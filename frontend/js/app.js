// ==========================================================================
// CLIENT STATE & SELECTORS
// ==========================================================================
const chatForm = document.getElementById('chat-form');
const queryInput = document.getElementById('query-input');
const chatMessages = document.getElementById('chat-messages');
const welcomeScreen = document.getElementById('welcome-screen');
const statusTag = document.getElementById('status-tag');
const statusDot = statusTag.querySelector('.status-dotDot');
const statusText = document.getElementById('status-text');
const btnIngest = document.getElementById('btn-ingest');
const syncOverlay = document.getElementById('sync-overlay');

let isGenerating = false;

// ==========================================================================
// SYSTEM INITIALIZATION & DIAGNOSTICS
// ==========================================================================
window.addEventListener('DOMContentLoaded', () => {
    checkSystemStatus();
});

async function checkSystemStatus() {
    try {
        const res = await fetch('/api/status');
        if (res.ok) {
            const data = await res.json();
            if (data.status === 'online') {
                updateStatus('connected', `Memory OS Online (${data.total_chunks} chunks)`);
            } else {
                updateStatus('idle', 'Memory Offline');
            }
        } else {
            updateStatus('error', 'API Server Error');
        }
    } catch (e) {
        updateStatus('error', 'Connection Refused');
        console.error("Status check failed:", e);
    }
}

function updateStatus(state, message) {
    statusDot.className = 'status-dotDot';
    statusDot.classList.add(state);
    statusText.textContent = message;
    
    if (state === 'error') {
        statusTag.style.borderColor = 'rgba(239, 68, 68, 0.2)';
    } else if (state === 'connected') {
        statusTag.style.borderColor = 'rgba(34, 197, 94, 0.2)';
    } else {
        statusTag.style.borderColor = 'var(--glass-border)';
    }
}

// ==========================================================================
// MANUAL MEMORY INGESTION TRIGGER (SYNC MEMORY)
// ==========================================================================
btnIngest.addEventListener('click', async () => {
    if (isGenerating) return;
    
    // Show Full-screen Blur Ingestion Loading Box
    syncOverlay.classList.add('show');
    updateStatus('indexing', 'Syncing Memory Database...');
    
    try {
        const res = await fetch('/api/ingest', { method: 'POST' });
        const data = await res.json();
        
        // Hide Overlay
        syncOverlay.classList.remove('show');
        
        if (res.ok && data.status === 'success') {
            alert("Memory Synchronization Successful! Your local ChromaDB vector memory is updated.");
            appendSystemMessage("Memory Database Sync Complete!", "I have successfully fetched the latest Zoom cloud files, archived them in your Box SecondBrain, and re-vectorized them inside ChromaDB. You can now search or ask questions about them!");
            checkSystemStatus();
        } else {
            alert(`Sync Failed: ${data.message || 'Unknown Error'}`);
            appendSystemMessage("Memory Sync Failed", `The ingestion script returned an error: ${data.error || 'Check local terminal logs for details.'}\n\n*Note: If Zoom API keys are inactive, I will automatically use the realistic local mock transcript seed files to verify system functionality.*`);
            checkSystemStatus();
        }
    } catch (e) {
        syncOverlay.classList.remove('show');
        alert("Connection lost during memory sync.");
        updateStatus('error', 'Sync Connection Failed');
        console.error(e);
    }
});

// ==========================================================================
// FORMAT RAG RESPONSES (MARKDOWN TO ELEGANT HTML)
// ==========================================================================
function formatResponseText(text) {
    if (!text) return "";
    
    // Escape standard HTML injection
    let formatted = text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
        
    // Bold formatting: **text**
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    
    // Headings: ### Text
    formatted = formatted.replace(/^###\s*(.*?)$/gm, "<h3>$1</h3>");
    
    // Unordered lists: - Text or * Text
    formatted = formatted.replace(/^[\-\*]\s+(.*?)$/gm, "<li>$1</li>");
    
    // Group adjacent <li> items inside a <ul> tag
    formatted = formatted.replace(/(<li>.*?<\/li>)+/gs, (match) => `<ul>${match}</ul>`);
    
    // Paragraph conversions: handle double newlines
    formatted = formatted.replace(/\n\n/g, "</p><p>");
    
    // Wrap entire content in a single paragraph if it doesn't start with standard tags
    if (!formatted.startsWith("<p>") && !formatted.startsWith("<h3>") && !formatted.startsWith("<ul>")) {
        formatted = `<p>${formatted}</p>`;
    }
    
    return formatted;
}

// ==========================================================================
// PRESET SUGGESTIONS HANDLER
// ==========================================================================
function sendPreset(text) {
    if (isGenerating) return;
    queryInput.value = text;
    chatForm.dispatchEvent(new Event('submit'));
}

// ==========================================================================
// CHAT MESSAGE UI GENERATION & SSE STREAMING
// ==========================================================================
chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const query = queryInput.value.trim();
    if (!query || isGenerating) return;
    
    isGenerating = true;
    queryInput.value = '';
    queryInput.disabled = true;
    
    // Hide Welcome Screen on first query
    if (welcomeScreen) {
        welcomeScreen.style.display = 'none';
    }
    
    // Append User Message
    appendMessage('user', query);
    
    // Scroll to bottom
    scrollToBottom();
    
    // Append Assistant Message Placeholder with Typing Dot indicator
    const assistantMsgElement = appendMessage('assistant', '', true);
    scrollToBottom();
    
    try {
        // Request SSE Stream from chat completions API
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ message: query })
        });
        
        // Remove typing indicator from bubble
        const bubble = assistantMsgElement.querySelector('.message-bubble');
        bubble.innerHTML = '';
        bubble.classList.remove('typing-bubble');
        assistantMsgElement.classList.add('streaming-active');
        
        if (!response.ok) {
            bubble.innerHTML = `<p class="status-text error">Error completing request (Status ${response.status_code}). Please verify Groq API configurations in backend/.env.</p>`;
            finalizeChatState();
            return;
        }
        
        // Setup SSE reader stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        
        let accumulatedText = "";
        
        // Cursor block
        const cursor = document.createElement('span');
        cursor.className = 'streaming-cursor';
        bubble.appendChild(cursor);
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const dataStr = line.slice(6).trim();
                    
                    if (dataStr === '[DONE]') {
                        break;
                    }
                    
                    try {
                        const parsed = JSON.parse(dataStr);
                        
                        if (parsed.error) {
                            bubble.innerHTML = `<p class="status-text error"><i class="fa-solid fa-triangle-exclamation"></i> Error: ${parsed.error}</p>`;
                            break;
                        }
                        
                        const contentDelta = parsed.choices?.[0]?.delta?.content;
                        if (contentDelta) {
                            accumulatedText += contentDelta;
                            // Format markdown and inject it alongside streaming cursor
                            bubble.innerHTML = formatResponseText(accumulatedText);
                            bubble.appendChild(cursor);
                            scrollToBottom();
                        }
                    } catch (err) {
                        // Skip unparsed chunks (e.g. comments, heartbeat pings)
                    }
                }
            }
        }
        
        // Remove stream cursor
        if (cursor.parentNode) {
            cursor.parentNode.removeChild(cursor);
        }
        
        assistantMsgElement.classList.remove('streaming-active');
        
    } catch (e) {
        console.error(e);
        const bubble = assistantMsgElement.querySelector('.message-bubble');
        bubble.innerHTML = `<p class="status-text error"><i class="fa-solid fa-triangle-exclamation"></i> Connection issue: Unable to reach Groq server. Check internet connectivity and key settings.</p>`;
    } finally {
        finalizeChatState();
    }
});

function finalizeChatState() {
    isGenerating = false;
    queryInput.disabled = false;
    queryInput.focus();
    checkSystemStatus();
}

function appendMessage(sender, text, isTyping = false) {
    const messageContainer = document.createElement('div');
    messageContainer.className = `message message-${sender}`;
    
    // Avatar
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.innerHTML = sender === 'user' ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-robot"></i>';
    
    // Bubble
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    
    if (isTyping) {
        bubble.classList.add('typing-bubble');
        bubble.innerHTML = `
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        `;
    } else {
        bubble.innerHTML = formatResponseText(text);
    }
    
    messageContainer.appendChild(avatar);
    messageContainer.appendChild(bubble);
    chatMessages.appendChild(messageContainer);
    
    return messageContainer;
}

function appendSystemMessage(title, description) {
    const messageContainer = document.createElement('div');
    messageContainer.className = 'message message-assistant';
    
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.style.background = 'linear-gradient(135deg, var(--accent-cyan), #3b82f6)';
    avatar.innerHTML = '<i class="fa-solid fa-gears"></i>';
    
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.style.borderLeftColor = 'var(--accent-cyan)';
    bubble.innerHTML = `
        <h3><i class="fa-solid fa-circle-check"></i> ${title}</h3>
        ${formatResponseText(description)}
    `;
    
    messageContainer.appendChild(avatar);
    messageContainer.appendChild(bubble);
    chatMessages.appendChild(messageContainer);
    scrollToBottom();
}

function scrollToBottom() {
    chatMessages.scrollTop = chatMessages.scrollHeight;
}
