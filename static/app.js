/* ===== EBS-INSIGHT CHAT APPLICATION ===== */

const API_BASE = "/api";
let sessionId = generateSessionId();
let isWaiting = false;

// ===== INITIALIZATION =====
document.addEventListener("DOMContentLoaded", () => {
    console.log("EBS-Insight Chat initialized");
    
    // Set session ID
    document.getElementById("session-id").textContent = sessionId;
    
    // Setup event listeners
    setupEventListeners();
    
    // Check health on load
    checkHealth();
});

// ===== EVENT LISTENERS =====
function setupEventListeners() {
    const input = document.getElementById("prompt-input");
    const sendBtn = document.getElementById("send-btn");
    
    // Send on Enter (not Shift+Enter)
    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    // Auto-resize textarea
    input.addEventListener("input", () => {
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 120) + "px";
        updateCharCount();
    });
}

// ===== MESSAGE SENDING =====
async function sendMessage() {
    const input = document.getElementById("prompt-input");
    const prompt = input.value.trim();
    
    if (!prompt) return;
    if (isWaiting) return;
    
    // Add user message to UI
    addMessage("user", prompt);
    input.value = "";
    input.style.height = "auto";
    updateCharCount();
    
    // Send to API
    try {
        isWaiting = true;
        document.getElementById("send-btn").disabled = true;
        showTypingIndicator();
        
        const startTime = performance.now();
        const response = await fetch(`${API_BASE}/chat`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                prompt: prompt,
                session_id: sessionId
            })
        });
        
        const endTime = performance.now();
        const duration = (endTime - startTime).toFixed(0);
        
        if (!response.ok) {
            const error = await response.json();
            addMessage("system", `❌ Hata: ${error.error || "Bilinmeyen hata"}`);
            return;
        }
        
        const data = await response.json();
        
        // Add assistant response
        const assistantMsg = `
            <p><strong>${data.verdict}</strong> <span class="message-verdict verdict-${data.verdict.toLowerCase()}">${getVerdictEmoji(data.verdict)} ${data.verdict}</span></p>
            <p>${data.response}</p>
            <small>Request ID: <code>${data.request_id}</code></small>
        `;
        
        addMessage("assistant", assistantMsg);
        
        // Show response time
        const responseTimeEl = document.getElementById("response-time");
        responseTimeEl.textContent = `⏱ ${duration}ms`;
        
        // Update details panel with raw data
        if (data.raw_data && data.raw_data.length > 0) {
            updateDetailsPanel(data);
        }
        
    } catch (err) {
        console.error("Error sending message:", err);
        addMessage("system", `❌ İletişim hatası: ${err.message}`);
    } finally {
        isWaiting = false;
        document.getElementById("send-btn").disabled = false;
        hideTypingIndicator();
    }
}

// ===== MESSAGE UI =====
function addMessage(type, content) {
    const container = document.getElementById("messages");
    const messageEl = document.createElement("div");
    messageEl.className = `message ${type}`;
    
    const now = new Date();
    const timeStr = now.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });
    
    messageEl.innerHTML = `
        <div class="message-content">${content}</div>
        <span class="message-time">${timeStr}</span>
    `;
    
    container.appendChild(messageEl);
    
    // Scroll to bottom
    container.scrollTop = container.scrollHeight;
}

function showTypingIndicator() {
    const indicator = document.getElementById("typing-indicator");
    indicator.classList.remove("hide");
    indicator.classList.add("show");
}

function hideTypingIndicator() {
    const indicator = document.getElementById("typing-indicator");
    indicator.classList.remove("show");
    indicator.classList.add("hide");
}

// ===== QUICK ACTIONS =====
function sendQuickPrompt(prompt) {
    const input = document.getElementById("prompt-input");
    input.value = prompt;
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
    updateCharCount();
    sendMessage();
}

// ===== HEALTH CHECK =====
async function checkHealth() {
    try {
        const response = await fetch("/health");
        const data = await response.json();
        
        const statusEl = document.getElementById("connection-status");
        if (response.ok) {
            statusEl.textContent = "● Bağlı";
            statusEl.className = "status-badge connected";
        } else {
            statusEl.textContent = "● Hata";
            statusEl.className = "status-badge error";
        }
        
        console.log("System health:", data);
    } catch (err) {
        const statusEl = document.getElementById("connection-status");
        statusEl.textContent = "● Disconnected";
        statusEl.className = "status-badge error";
        console.error("Health check failed:", err);
    }
}

// ===== UTILITY FUNCTIONS =====
function generateSessionId() {
    return `sess_${Math.random().toString(36).substr(2, 9)}`;
}

function updateCharCount() {
    const input = document.getElementById("prompt-input");
    const count = input.value.length;
    const maxCount = 500;
    document.getElementById("char-count").textContent = `${count} / ${maxCount}`;
}

function getVerdictEmoji(verdict) {
    const emojis = {
        "OK": "✅",
        "WARN": "⚠️",
        "CRIT": "🔴",
        "UNKNOWN": "❓"
    };
    return emojis[verdict] || "❓";
}

function updateDetailsPanel(data) {
    const content = document.getElementById("details-content");
    
    let html = `
        <h4>Request Metadata</h4>
        <ul>
            <li><strong>Request ID:</strong> <code>${data.request_id}</code></li>
            <li><strong>Intent:</strong> ${data.intent} (${(data.intent_confidence * 100).toFixed(1)}%)</li>
            <li><strong>Execution Time:</strong> ${data.execution_time_ms.toFixed(2)}ms</li>
            <li><strong>Timestamp:</strong> ${new Date(data.timestamp).toLocaleString("tr-TR")}</li>
        </ul>
    `;
    
    // Add raw data table if available
    if (data.raw_data && data.raw_data.length > 0) {
        html += `
            <h4>Ham Veri (${data.raw_data.length} / ${data.raw_data_count || data.raw_data.length} satır)</h4>
            <div class="raw-data-table">
                <table>
                    <thead>
                        <tr>
                            ${Object.keys(data.raw_data[0]).map(key => `<th>${key}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${data.raw_data.map(row => `
                            <tr>
                                ${Object.values(row).map(val => `<td>${val || '-'}</td>`).join('')}
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }
    
    content.innerHTML = html;
    
    // Auto-open details panel when data is available
    const panel = document.getElementById("details-panel");
    if (data.raw_data && data.raw_data.length > 0) {
        panel.classList.remove("hidden");
    }
}

function clearChat() {
    const container = document.getElementById("messages");
    container.innerHTML = `
        <div class="message system">
            <div class="message-content">
                <p>💬 Sohbet temizlendi. Yeni sorunuzu yazabilirsiniz.</p>
            </div>
            <span class="message-time">Şimdi</span>
        </div>
    `;
    sessionId = generateSessionId();
    document.getElementById("session-id").textContent = sessionId;
}

function toggleDetailsPanel() {
    const panel = document.getElementById("details-panel");
    panel.classList.toggle("hidden");
}
