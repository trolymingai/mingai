package personal

import (
	"context"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/google/uuid"

	"github.com/nextlevelbuilder/goclaw/internal/bus"
	"github.com/nextlevelbuilder/goclaw/internal/channels"
	"github.com/nextlevelbuilder/goclaw/internal/channels/typing"
	"github.com/nextlevelbuilder/goclaw/internal/channels/zalo/personal/protocol"
	"github.com/nextlevelbuilder/goclaw/internal/config"
	"github.com/nextlevelbuilder/goclaw/internal/store"
)

// Channel connects to Zalo Personal Chat via the internal protocol port (from zcago, MIT).
// WARNING: Zalo Personal is an unofficial, reverse-engineered integration. Account may be locked/banned.
type Channel struct {
	*channels.BaseChannel
	config      config.ZaloPersonalConfig
	typingCtrls sync.Map // threadID → *typing.Controller

	mu       sync.RWMutex // protects sess and listener
	sess     *protocol.Session
	listener *protocol.Listener

	groupNames sync.Map // threadID string -> groupName string
	contactRegistry sync.Map // normalized name -> uid string

	// Pre-loaded credentials (from DB or from file/QR as fallback).
	preloadedCreds *protocol.Credentials

	stopCh   chan struct{}
	stopOnce sync.Once
}

// New creates a new Zalo Personal channel from config.
func New(cfg config.ZaloPersonalConfig, msgBus *bus.MessageBus, pairingSvc store.PairingStore, pendingStore store.PendingMessageStore) (*Channel, error) {
	base := channels.NewBaseChannel(channels.TypeZaloPersonal, msgBus, cfg.AllowFrom)

	if cfg.DMPolicy == "" {
		cfg.DMPolicy = "allowlist"
	}
	if cfg.GroupPolicy == "" {
		cfg.GroupPolicy = "allowlist"
	}
	base.ValidatePolicy(cfg.DMPolicy, cfg.GroupPolicy)

	historyLimit := cfg.HistoryLimit
	if historyLimit == 0 {
		historyLimit = channels.DefaultGroupHistoryLimit
	}

	requireMention := true
	if cfg.RequireMention != nil {
		requireMention = *cfg.RequireMention
	}

	ch := &Channel{
		BaseChannel: base,
		config:      cfg,
		stopCh:      make(chan struct{}),
	}
	ch.SetPairingService(pairingSvc)
	ch.SetGroupHistory(channels.MakeHistory(channels.TypeZaloPersonal, pendingStore, base.TenantID()))
	ch.SetHistoryLimit(historyLimit)
	ch.SetRequireMention(requireMention)
	ch.initContactRegistry()
	return ch, nil
}

// BlockReplyEnabled returns the per-channel block_reply override (nil = inherit gateway default).
func (c *Channel) BlockReplyEnabled() *bool { return c.config.BlockReply }

// ChatBehaviorConfig returns the per-channel chat_behavior override.
func (c *Channel) ChatBehaviorConfig() *config.ChatBehaviorConfig { return c.config.ChatBehavior }

// session returns the current session snapshot (thread-safe).
func (c *Channel) session() *protocol.Session {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.sess
}

// getListener returns the current listener snapshot (thread-safe).
func (c *Channel) getListener() *protocol.Listener {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.listener
}

// Start authenticates and begins listening for Zalo messages.
func (c *Channel) Start(ctx context.Context) error {
	if gh := c.GroupHistory(); gh != nil {
		gh.StartFlusher()
	}
	slog.Warn("security.unofficial_api",
		"channel", "zalo_personal",
		"msg", "Zalo Personal is unofficial and reverse-engineered. Account may be locked/banned. Use at own risk.",
	)

	sess, err := c.authenticate(ctx)
	if err != nil {
		return fmt.Errorf("zalo_personal auth: %w", err)
	}

	ln, err := protocol.NewListener(sess)
	if err != nil {
		return fmt.Errorf("zalo_personal listener: %w", err)
	}
	if err := ln.Start(ctx); err != nil {
		return fmt.Errorf("zalo_personal listener start: %w", err)
	}

	c.mu.Lock()
	c.sess = sess
	c.listener = ln
	c.mu.Unlock()

	slog.Info("zalo_personal connected", "uid", sess.UID)

	c.SetRunning(true)
	go c.listenLoop(ctx)
	go c.autoAcceptFriendLoop(ctx)
	go c.LoadGroupNames(ctx)
	go func() {
		ticker := time.NewTicker(3 * time.Minute)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-c.stopCh:
				return
			case <-ticker.C:
				c.LoadGroupNames(ctx)
			}
		}
	}()

	slog.Info("zalo_personal listener loop started")
	return nil
}

// LoadGroupNames fetches and caches group names from Zalo API.
func (c *Channel) LoadGroupNames(ctx context.Context) {
	sess := c.session()
	if sess == nil {
		return
	}
	groups, err := protocol.FetchGroups(ctx, sess)
	if err != nil {
		slog.Warn("zalo_personal: failed to fetch groups for naming", "error", err)
		return
	}
	for _, g := range groups {
		if g.GroupID != "" && g.Name != "" {
			c.groupNames.Store(g.GroupID, g.Name)
			slog.Info("zalo_personal: cached group name", "group_id", g.GroupID, "name", g.Name)
		}
	}
}

// GetGroupName returns the cached friendly group name, or refreshes if missing.
func (c *Channel) GetGroupName(ctx context.Context, threadID string) string {
	if val, ok := c.groupNames.Load(threadID); ok {
		if s, ok := val.(string); ok && s != "" {
			return s
		}
	}
	c.LoadGroupNames(ctx)
	if val, ok := c.groupNames.Load(threadID); ok {
		if s, ok := val.(string); ok && s != "" {
			return s
		}
	}
	return ""
}

// SetPendingCompaction configures LLM-based auto-compaction for pending messages.
func (c *Channel) SetPendingCompaction(cfg *channels.CompactionConfig) {
	if gh := c.GroupHistory(); gh != nil {
		gh.SetCompactionConfig(cfg)
	}
}

// SetPendingHistoryTenantID propagates tenant_id to the pending history for DB operations.
func (c *Channel) SetPendingHistoryTenantID(id uuid.UUID) {
	if gh := c.GroupHistory(); gh != nil {
		gh.SetTenantID(id)
	}
}

// Stop gracefully shuts down the Zalo Personal channel.
func (c *Channel) Stop(_ context.Context) error {
	if gh := c.GroupHistory(); gh != nil {
		gh.StopFlusher()
	}
	slog.Info("stopping zalo_personal channel")
	c.stopOnce.Do(func() { close(c.stopCh) })
	c.typingCtrls.Range(func(key, val any) bool {
		if ctrl, ok := val.(*typing.Controller); ok {
			ctrl.Stop()
		}
		c.typingCtrls.Delete(key)
		return true
	})
	if ln := c.getListener(); ln != nil {
		ln.Stop()
	}
	c.SetRunning(false)
	return nil
}

// autoAcceptFriendLoop periodically fetches and auto-accepts pending friend requests.
func (c *Channel) autoAcceptFriendLoop(ctx context.Context) {
	ticker := time.NewTicker(20 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-c.stopCh:
			return
		case <-ticker.C:
			sess := c.session()
			if sess == nil || sess.SecretKey == "" {
				continue
			}
			fids, err := protocol.FetchPendingFriendRequests(ctx, sess)
			if err != nil || len(fids) == 0 {
				continue
			}
			for _, fid := range fids {
				slog.Info("zalo_personal: auto-accepting pending friend request", "fid", fid)
				if err := protocol.AcceptFriendRequest(ctx, sess, fid); err != nil {
					slog.Warn("zalo_personal: failed to accept friend request", "fid", fid, "error", err)
				} else {
					slog.Info("zalo_personal: successfully auto-accepted friend request", "fid", fid)
				}
			}
		}
	}
}
