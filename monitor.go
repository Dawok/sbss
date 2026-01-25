package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/signal"
	"regexp"
	"strconv"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

// Config represents the configuration structure
type Config struct {
	URL                   string  `json:"url"`
	Threads               int     `json:"threads"`
	MaxPageViews          int64   `json:"max_page_views"`
	RequestInterval       float64 `json:"request_interval"`
	DiscordWebhook        string  `json:"discord_webhook"`
	MaxConsecutiveErrors  int64   `json:"max_consecutive_errors"`
}

// APIResponse represents the API response structure
type APIResponse struct {
	ResponseDataForDetail struct {
		Title    string `json:"TITLE"`
		ClickCnt int64  `json:"CLICK_CNT"`
	} `json:"Response_Data_For_Detail"`
}

// DiscordEmbed represents a Discord webhook embed
type DiscordEmbed struct {
	Title       string       `json:"title"`
	Description string       `json:"description"`
	Color       int          `json:"color"`
	URL         string       `json:"url,omitempty"`
	Footer      *EmbedFooter `json:"footer,omitempty"`
}

type EmbedFooter struct {
	Text string `json:"text"`
}

type DiscordWebhook struct {
	Embeds []DiscordEmbed `json:"embeds"`
}

// Monitor represents the page view monitor
type Monitor struct {
	config              Config
	apiURL              string
	title               string
	hostname            string
	pageViews           int64
	totalRequests       int64
	failedRequests      int64
	consecutiveErrors   int64
	initialUpdateDone   bool
	errorSent           bool
	startTime           time.Time
	stopChan            chan struct{}
	stopOnce            sync.Once
	mu                  sync.Mutex
	client              *http.Client
}

// NewMonitor creates a new Monitor instance
func NewMonitor(configPath string) (*Monitor, error) {
	config, err := loadConfig(configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to load config: %w", err)
	}

	apiURL, err := constructAPIURL(config.URL)
	if err != nil {
		return nil, fmt.Errorf("failed to construct API URL: %w", err)
	}

	hostname, _ := os.Hostname()
	if hostname == "" {
		hostname = "unknown"
	}

	m := &Monitor{
		config:   config,
		apiURL:   apiURL,
		hostname: hostname,
		stopChan: make(chan struct{}),
		client: &http.Client{
			Timeout: 30 * time.Second, // Increased from 10s to 30s
		},
	}

	// Fetch initial title
	m.title = m.fetchInitialTitle()

	return m, nil
}

func loadConfig(path string) (Config, error) {
	var config Config
	file, err := os.ReadFile(path)
	if err != nil {
		return config, err
	}

	err = json.Unmarshal(file, &config)
	if err != nil {
		return config, err
	}

	// Set defaults
	if config.RequestInterval == 0 {
		config.RequestInterval = 1.0
	}
	if config.MaxConsecutiveErrors == 0 {
		config.MaxConsecutiveErrors = 50 // More tolerant default
	}

	return config, nil
}

func constructAPIURL(url string) (string, error) {
	re := regexp.MustCompile(`board_no=(\d+)`)
	matches := re.FindStringSubmatch(url)
	if len(matches) < 2 {
		return "", fmt.Errorf("invalid URL format: could not find 'board_no' parameter")
	}

	boardNo := matches[1]
	timestamp := time.Now().UnixMilli()
	apiURL := fmt.Sprintf(
		"https://api.board.sbs.co.kr/bbs/V2.0/basic/board/detail/%s?callback=boardViewCallback_inkigayo_pt01&action_type=callback&board_code=inkigayo_pt01&jwt-token=&_=%d",
		boardNo, timestamp,
	)

	return apiURL, nil
}

func (m *Monitor) fetchInitialTitle() string {
	views, title, err := m.fetchPageViews()
	if err != nil {
		fmt.Printf("Error fetching initial title: %v\n", err)
		return "Unknown Title"
	}
	m.pageViews = views
	return title
}

func (m *Monitor) fetchPageViews() (int64, string, error) {
	// Update timestamp in URL
	timestamp := time.Now().UnixMilli()
	re := regexp.MustCompile(`_=\d+`)
	url := re.ReplaceAllString(m.apiURL, fmt.Sprintf("_=%d", timestamp))

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return 0, "", err
	}

	req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

	resp, err := m.client.Do(req)
	if err != nil {
		return 0, "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return 0, "", fmt.Errorf("HTTP error: %d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return 0, "", err
	}

	// Extract JSON from JSONP
	re = regexp.MustCompile(`\((.*)\)`)
	matches := re.FindSubmatch(body)
	if len(matches) < 2 {
		return 0, "", fmt.Errorf("invalid JSONP response format")
	}

	var apiResp APIResponse
	err = json.Unmarshal(matches[1], &apiResp)
	if err != nil {
		return 0, "", err
	}

	clickCnt := apiResp.ResponseDataForDetail.ClickCnt
	return clickCnt, apiResp.ResponseDataForDetail.Title, nil
}

func (m *Monitor) sendDiscordWebhook(embed DiscordEmbed) error {
	if m.config.DiscordWebhook == "" {
		return nil
	}

	webhook := DiscordWebhook{
		Embeds: []DiscordEmbed{embed},
	}

	data, err := json.Marshal(webhook)
	if err != nil {
		return err
	}

	resp, err := http.Post(m.config.DiscordWebhook, "application/json", bytes.NewBuffer(data))
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusNoContent {
		return fmt.Errorf("webhook returned status: %d", resp.StatusCode)
	}

	return nil
}

func (m *Monitor) sendStartWebhook() {
	currentTime := time.Now().Format("2006-01-02 15:04:05")
	description := fmt.Sprintf(
		"**Current Page Views:** %s\n**Target Page Views:** %s\n**Thread Count:** %d\n**Request Interval:** %.1fs",
		formatNumber(m.pageViews),
		formatNumber(m.config.MaxPageViews),
		m.config.Threads,
		m.config.RequestInterval,
	)

	embed := DiscordEmbed{
		Title:       fmt.Sprintf("📊 Script Started for '%s' on %s", m.title, m.hostname),
		Description: description,
		Color:       3447003,
		URL:         m.config.URL,
		Footer:      &EmbedFooter{Text: fmt.Sprintf("Started at %s", currentTime)},
	}

	if err := m.sendDiscordWebhook(embed); err != nil {
		fmt.Printf("[%s] Error sending start webhook: %v\n", currentTime, err)
	} else {
		fmt.Printf("[%s] Discord start notification sent\n", currentTime)
	}
}

func (m *Monitor) sendThresholdWebhook() {
	currentTime := time.Now().Format("2006-01-02 15:04:05")
	duration := time.Since(m.startTime).Seconds()
	successRate := float64(m.totalRequests-m.failedRequests) / float64(max(m.totalRequests, 1)) * 100

	description := fmt.Sprintf(
		"**Page Views:** %s\n**Target:** %s\n**Duration:** %.1fs\n**Total Requests:** %s\n**Failed Requests:** %s\n**Success Rate:** %.1f%%",
		formatNumber(m.pageViews),
		formatNumber(m.config.MaxPageViews),
		duration,
		formatNumber(m.totalRequests),
		formatNumber(m.failedRequests),
		successRate,
	)

	embed := DiscordEmbed{
		Title:       fmt.Sprintf("🎯 Target Reached on %s!", m.hostname),
		Description: description,
		Color:       65280,
		URL:         m.config.URL,
		Footer:      &EmbedFooter{Text: fmt.Sprintf("Completed at %s", currentTime)},
	}

	if err := m.sendDiscordWebhook(embed); err != nil {
		fmt.Printf("[%s] Error sending threshold webhook: %v\n", currentTime, err)
	} else {
		fmt.Printf("[%s] Discord threshold notification sent\n", currentTime)
	}
}

func (m *Monitor) sendErrorWebhook(errorMsg string) {
	currentTime := time.Now().Format("2006-01-02 15:04:05")
	description := fmt.Sprintf(
		"**Error:** %s\n**Consecutive Errors:** %d",
		errorMsg,
		m.consecutiveErrors,
	)

	embed := DiscordEmbed{
		Title:       fmt.Sprintf("⚠️ Error on %s", m.hostname),
		Description: description,
		Color:       15158332,
		Footer:      &EmbedFooter{Text: fmt.Sprintf("Error at %s", currentTime)},
	}

	if err := m.sendDiscordWebhook(embed); err != nil {
		fmt.Printf("[%s] Error sending error webhook: %v\n", currentTime, err)
	} else {
		fmt.Printf("[%s] Discord error notification sent\n", currentTime)
	}
}

func (m *Monitor) worker(workerID int, wg *sync.WaitGroup) {
	defer wg.Done()
	fmt.Printf("[Worker-%d] Started\n", workerID)

	ticker := time.NewTicker(time.Duration(m.config.RequestInterval * float64(time.Second)))
	defer ticker.Stop()

	for {
		select {
		case <-m.stopChan:
			fmt.Printf("[Worker-%d] Stopped\n", workerID)
			return
		case <-ticker.C:
			newViews, _, err := m.fetchPageViews()
			currentTime := time.Now().Format("2006-01-02 15:04:05")

			if err != nil {
				atomic.AddInt64(&m.failedRequests, 1)
				atomic.AddInt64(&m.consecutiveErrors, 1)
				
				errCount := atomic.LoadInt64(&m.consecutiveErrors)
				fmt.Printf("[%s] [Worker-%d] Error: %v\n", currentTime, workerID, err)

				// Send webhook on first error or every 10 consecutive errors
				if errCount == 1 || errCount%10 == 0 {
					m.sendErrorWebhook(err.Error())
				}

				// Stop if too many consecutive errors
				maxErrors := m.config.MaxConsecutiveErrors
				if errCount >= maxErrors {
					fmt.Printf("[%s] Too many consecutive errors (%d). Stopping...\n", currentTime, errCount)
					m.stopOnce.Do(func() { close(m.stopChan) })
					return
				}
				continue
			}

			atomic.AddInt64(&m.totalRequests, 1)
			atomic.StoreInt64(&m.consecutiveErrors, 0)

			m.mu.Lock()
			oldViews := m.pageViews
			viewsChanged := newViews != oldViews || !m.initialUpdateDone

			if viewsChanged {
				m.pageViews = newViews

				if !m.initialUpdateDone {
					m.initialUpdateDone = true
					m.startTime = time.Now()
					go m.sendStartWebhook()
				}

				change := newViews - oldViews
				changeStr := ""
				if oldViews > 0 && change > 0 {
					changeStr = fmt.Sprintf(" (+%s)", formatNumber(change))
				}
				fmt.Printf("[%s] [Worker-%d] Page Views: %s%s\n", currentTime, workerID, formatNumber(newViews), changeStr)

				// Check if threshold reached
				if m.config.MaxPageViews > 0 && newViews >= m.config.MaxPageViews {
					fmt.Printf("[%s] Target reached! Stopping all workers...\n", currentTime)
					m.mu.Unlock()
					go m.sendThresholdWebhook()
					m.stopOnce.Do(func() { close(m.stopChan) })
					return
				}
			}
			m.mu.Unlock()
		}
	}
}

func (m *Monitor) Run() {
	fmt.Println("\n" + repeatString("=", 60))
	fmt.Printf("Page View Monitor - %s\n", m.title)
	fmt.Println(repeatString("=", 60))
	fmt.Printf("Target: %s page views\n", formatNumber(m.config.MaxPageViews))
	fmt.Printf("Workers: %d\n", m.config.Threads)
	fmt.Printf("Interval: %.1fs\n", m.config.RequestInterval)
	fmt.Printf("Hostname: %s\n", m.hostname)
	fmt.Println(repeatString("=", 60) + "\n")

	// Setup signal handling for graceful shutdown
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, os.Interrupt, syscall.SIGTERM)

	go func() {
		<-sigChan
		fmt.Println("\n\nReceived interrupt signal. Stopping gracefully...")
		m.stopOnce.Do(func() { close(m.stopChan) })
	}()

	// Start worker goroutines
	var wg sync.WaitGroup
	for i := 0; i < m.config.Threads; i++ {
		wg.Add(1)
		go m.worker(i, &wg)
	}

	// Wait for all workers to complete
	wg.Wait()

	// Print final statistics
	duration := time.Since(m.startTime).Seconds()
	successRate := float64(m.totalRequests-m.failedRequests) / float64(max(m.totalRequests, 1)) * 100

	fmt.Println("\n" + repeatString("=", 60))
	fmt.Println("Final Statistics:")
	fmt.Printf("  Final Page Views: %s\n", formatNumber(m.pageViews))
	fmt.Printf("  Total Requests: %s\n", formatNumber(m.totalRequests))
	fmt.Printf("  Failed Requests: %s\n", formatNumber(m.failedRequests))
	fmt.Printf("  Success Rate: %.1f%%\n", successRate)
	fmt.Printf("  Duration: %.1fs\n", duration)
	fmt.Println(repeatString("=", 60) + "\n")
}

func formatNumber(n int64) string {
	str := strconv.FormatInt(n, 10)
	var result []byte
	for i, digit := range str {
		if i > 0 && (len(str)-i)%3 == 0 {
			result = append(result, ',')
		}
		result = append(result, byte(digit))
	}
	return string(result)
}

func max(a, b int64) int64 {
	if a > b {
		return a
	}
	return b
}

func repeatString(s string, count int) string {
	if count <= 0 {
		return ""
	}
	result := make([]byte, len(s)*count)
	bp := copy(result, s)
	for bp < len(result) {
		copy(result[bp:], result[:bp])
		bp *= 2
	}
	return string(result)
}

func main() {
	monitor, err := NewMonitor("config.json")
	if err != nil {
		fmt.Printf("Fatal error: %v\n", err)
		os.Exit(1)
	}

	monitor.Run()
}