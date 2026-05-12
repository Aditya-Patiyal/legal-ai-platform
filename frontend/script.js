const state = {
  user: null,
  documents: [],
  selectedDocumentId: null,
};

// Hide auth-related elements on page load
document.addEventListener('DOMContentLoaded', () => {
  const authBtn = byId('nav-auth-btn');
  if (authBtn) authBtn.style.display = 'none';
  const logoutBtn = byId('nav-logout-btn');
  if (logoutBtn) logoutBtn.style.display = 'none';
});

function setSessionToken(token) {
  document.cookie = `session_token=${token}; path=/; max-age=${60 * 60 * 24 * 7}; SameSite=Lax`;
}

function getSessionToken() {
  const match = document.cookie.match(/session_token=([^;]+)/);
  return match ? match[1] : null;
}

function clearSessionToken() {
  document.cookie = 'session_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
}

async function api(path, options = {}) {
  const token = getSessionToken();
  const headers = {
    ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { 'X-Session-Token': token } : {}),
    ...(options.headers || {}),
  };
  
  const response = await fetch(path, {
    credentials: 'include',
    headers,
    ...options,
  });
  
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(data.detail || 'Request failed');
  }
  
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) {
    return response.json();
  }
  return response;
}

function $(selector) {
  return document.querySelector(selector);
}

function byId(id) {
  return document.getElementById(id);
}

function setText(id, text) {
  const element = byId(id);
  if (element) {
    element.textContent = text;
  }
}

function setHTML(id, html) {
  const element = byId(id);
  if (element) {
    element.innerHTML = html;
  }
}

function showStatus(id, message, type = 'loading') {
  const element = byId(id);
  if (element) {
    element.textContent = message;
    element.className = `form-status visible ${type}`;
  }
}

function hideStatus(id) {
  const element = byId(id);
  if (element) {
    element.className = 'form-status';
  }
}

function escapeHtml(value) {
  if (value === null || value === undefined) return '';
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function renderMarkdown(text) {
  if (typeof marked !== 'undefined') {
    return marked.parse(text || '');
  }
  return `<p>${escapeHtml(text)}</p>`;
}

let _docPollTimer = null;

async function pollDocumentReady(documentId, statusId = null, maxAttempts = 25, intervalMs = 2000) {
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
    const data = await api(`/api/documents/${documentId}`);
    const status = data.document.upload_status;
    if (status === 'ready') return data.document;
    if (status === 'error') throw new Error('Document processing failed. Please try uploading again.');
    if (statusId) {
      const dots = '.'.repeat((i % 3) + 1);
      showStatus(statusId, `Processing document${dots}`, 'loading');
    }
  }
  throw new Error('Document processing timed out. Please refresh and try again.');
}

async function streamChatFetch(endpoint, body, onToken, onDone) {
  const token = getSessionToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { 'X-Session-Token': token } : {}),
  };
  const response = await fetch(endpoint, {
    method: 'POST',
    credentials: 'include',
    headers,
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const errData = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(errData.detail || 'Request failed');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let doneReceived = false;

  function processLines(text) {
    const lines = text.split('\n');
    const remainder = lines.pop();
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event = JSON.parse(line.slice(6));
          if (event.type === 'token') onToken(event.content);
          else if (event.type === 'done') { onDone(event); doneReceived = true; }
        } catch (_) {}
      }
    }
    return remainder;
  }

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = processLines(buffer);
  }
  // Process any remaining data left in the buffer
  if (buffer.trim()) {
    processLines(buffer + '\n');
  }
  return doneReceived;
}

function appendStreamingMessage(container) {
  if (!container) return { appendToken: () => {}, finalize: () => '' };
  const emptyState = container.querySelector('.chatbot-empty');
  if (emptyState) emptyState.remove();
  const div = document.createElement('div');
  div.className = 'chatbot-message chatbot-message-assistant';
  const bubble = document.createElement('div');
  bubble.className = 'chatbot-bubble chatbot-bubble-assistant';
  const textDiv = document.createElement('div');
  textDiv.className = 'chatbot-text chatbot-streaming';
  bubble.appendChild(textDiv);
  div.appendChild(bubble);
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  let rawText = '';
  return {
    appendToken(token) {
      rawText += token;
      textDiv.textContent = rawText;
      container.scrollTop = container.scrollHeight;
    },
    finalize() {
      textDiv.classList.remove('chatbot-streaming');
      textDiv.classList.add('chatbot-markdown');
      textDiv.innerHTML = renderMarkdown(rawText);
      container.scrollTop = container.scrollHeight;
      return rawText;
    },
  };
}

async function hydrateUser() {
  // Authentication disabled: return mock user
  state.user = { id: 1, name: "Guest User", email: "guest@example.com" };
  document.querySelectorAll('[data-auth-name]').forEach((node) => {
    node.textContent = state.user.name;
  });
  return state.user;
}

async function handleSignup(event) {
  event.preventDefault();
  const statusId = 'signup-status';
  
  try {
    showStatus(statusId, 'Creating your account...', 'loading');
    
    const payload = {
      name: byId('signup-name').value.trim(),
      email: byId('signup-email').value.trim(),
      password: byId('signup-password').value,
    };
    
    if (!payload.name || !payload.email || !payload.password) {
      throw new Error('Please fill in all fields');
    }
    
    if (payload.password.length < 4) {
      throw new Error('Password must be at least 4 characters');
    }
    
    const data = await api('/api/auth/signup', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    
    setSessionToken(data.session_token);
    showStatus(statusId, 'Account created! Redirecting...', 'success');
    
    setTimeout(() => {
      window.location.href = '/dashboard';
    }, 500);
  } catch (error) {
    showStatus(statusId, error.message, 'error');
  }
}

async function handleLogin(event) {
  event.preventDefault();
  const statusId = 'login-status';
  
  try {
    showStatus(statusId, 'Signing in...', 'loading');
    
    const payload = {
      email: byId('login-email').value.trim(),
      password: byId('login-password').value,
    };
    
    if (!payload.email || !payload.password) {
      throw new Error('Please fill in all fields');
    }
    
    const data = await api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    
    setSessionToken(data.session_token);
    showStatus(statusId, 'Success! Redirecting...', 'success');
    
    setTimeout(() => {
      window.location.href = '/dashboard';
    }, 500);
  } catch (error) {
    showStatus(statusId, error.message, 'error');
  }
}

async function handleLogout() {
  try {
    await api('/api/auth/logout', { method: 'POST' });
  } catch {
    // Ignore logout errors
  }
  clearSessionToken();
  window.location.href = '/';
}

function renderDocuments(documents) {
  const container = byId('document-list');
  if (!container) {
    return;
  }
  if (!documents.length) {
    container.innerHTML = `
      <div class="doc-empty">
        <svg class="doc-empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
          <line x1="12" y1="18" x2="12" y2="12"></line>
          <line x1="9" y1="15" x2="15" y2="15"></line>
        </svg>
        <p class="doc-empty-title">No documents yet</p>
        <p class="doc-empty-hint">Upload a PDF or DOCX file above to get started with AI-powered analysis</p>
      </div>
    `;
    return;
  }
  container.innerHTML = documents
    .map(
      (doc) => `
        <div class="doc-item">
          <div class="doc-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
            </svg>
          </div>
          <div class="doc-info">
            <div class="doc-name">${escapeHtml(doc.filename)}</div>
            <div class="doc-meta">
              <span class="doc-status doc-status-${doc.upload_status}">${doc.upload_status === 'ready' ? '✓ Ready' : doc.upload_status}</span>
              <span class="doc-chunks">${doc.chunk_count} chunks indexed</span>
            </div>
          </div>
          <div class="doc-actions">
            <a class="btn btn-primary btn-sm" href="/chat?documentId=${doc.id}">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
              </svg>
              Chat
            </a>
            <button class="btn btn-secondary btn-sm" type="button" onclick="runClause(${doc.id})">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="8"></circle>
                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              </svg>
              Clauses
            </button>
            <button class="btn btn-secondary btn-sm" type="button" onclick="runRisk(${doc.id})">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
              </svg>
              Risk
            </button>
            <button class="btn btn-danger btn-sm" type="button" onclick="deleteDocument(${doc.id}, '${escapeHtml(doc.filename).replace(/'/g, "\\'")}')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
              </svg>
              Delete
            </button>
          </div>
        </div>
      `
    )
    .join('');
}

async function deleteDocument(documentId, filename) {
  if (!confirm(`Are you sure you want to delete "${filename}"? This will also delete all chat history for this document.`)) {
    return;
  }
  try {
    await api(`/api/documents/${documentId}`, { method: 'DELETE' });
    await loadDocuments();
    setHTML('analysis-output', `
      <div class="analysis-empty">
        <svg class="analysis-empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="16" x2="12" y2="12"></line>
          <line x1="12" y1="8" x2="12.01" y2="8"></line>
        </svg>
        <p class="analysis-empty-title">Document deleted</p>
        <p class="analysis-empty-hint">Upload a new document to continue</p>
      </div>
    `);
  } catch (error) {
    alert('Failed to delete document: ' + error.message);
  }
}

async function clearChatHistory(documentId) {
  if (!confirm('Are you sure you want to clear all chat history for this document?')) {
    return;
  }
  try {
    await api(`/api/chat-history/${documentId}`, { method: 'DELETE' });
    const container = byId('chat-messages');
    if (container) {
      container.innerHTML = '<div class="text-muted">Chat history cleared. Ask a new question to get started.</div>';
    }
  } catch (error) {
    alert('Failed to clear chat history: ' + error.message);
  }
}

async function loadDocuments(selectId) {
  const data = await api('/api/documents');
  state.documents = data.documents;
  renderDocuments(data.documents);
  const select = selectId ? byId(selectId) : null;
  if (select) {
    select.innerHTML = data.documents.map((doc) => `<option value="${doc.id}">${escapeHtml(doc.filename)}</option>`).join('');
    if (data.documents.length && !state.selectedDocumentId) {
      state.selectedDocumentId = Number(data.documents[0].id);
      select.value = String(state.selectedDocumentId);
    }
  }
  // Auto-refresh while any document is still processing
  const hasProcessing = data.documents.some((d) => d.upload_status === 'processing');
  if (hasProcessing && !_docPollTimer) {
    _docPollTimer = setTimeout(async () => {
      _docPollTimer = null;
      await loadDocuments(selectId);
    }, 3000);
  } else if (!hasProcessing && _docPollTimer) {
    clearTimeout(_docPollTimer);
    _docPollTimer = null;
  }
}

async function handleUpload(event) {
  event.preventDefault();
  const statusId = 'upload-status';
  
  try {
    const fileInput = byId('document-file');
    if (!fileInput.files.length) {
      throw new Error('Please select a PDF or DOCX file');
    }
    
    const file = fileInput.files[0];
    const validTypes = ['.pdf', '.docx'];
    const ext = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));
    
    if (!validTypes.includes(ext)) {
      throw new Error('Only PDF and DOCX files are supported');
    }
    
    showStatus(statusId, `Uploading ${file.name}...`, 'loading');
    
    const formData = new FormData();
    formData.append('file', file);
    
    const data = await api('/api/documents/upload', {
      method: 'POST',
      body: formData,
    });
    
    fileInput.value = '';
    await loadDocuments();
    
    if (data.document.upload_status === 'processing') {
      showStatus(statusId, `Processing ${data.document.filename}...`, 'loading');
      const readyDoc = await pollDocumentReady(data.document.id, statusId);
      
      // Update the local documents list in state with the ready document
      const index = state.documents.findIndex(d => d.id === readyDoc.id);
      if (index !== -1) {
        state.documents[index] = readyDoc;
      } else {
        state.documents.unshift(readyDoc);
      }
      await loadDocuments();
    }
    showStatus(statusId, `Successfully uploaded ${data.document.filename}`, 'success');
  } catch (error) {
    showStatus(statusId, error.message, 'error');
  }
}

async function runClause(documentId) {
  try {
    const clauseType = byId('clause-type') ? byId('clause-type').value : 'termination';
    
    setHTML('analysis-output', '<div class="text-muted">Extracting clause...</div>');
    
    const data = await api('/api/clauses/extract', {
      method: 'POST',
      body: JSON.stringify({ document_id: documentId, clause_type: clauseType }),
    });
    
    const riskClass = `badge-${data.risk_level.toLowerCase()}`;
    
    setHTML(
      'analysis-output',
      `
        <div class="analysis-card glass-card">
          <div class="analysis-header">
            <h3 class="analysis-title">${escapeHtml(data.clause_type)} Clause</h3>
            <span class="badge ${riskClass}">${escapeHtml(data.risk_level)} Risk</span>
          </div>
          <div class="analysis-snippet">${escapeHtml(data.snippet || 'No matching clause found in the document.')}</div>
          <p class="analysis-content">${escapeHtml(data.explanation)}</p>
        </div>
      `
    );
  } catch (error) {
    setHTML('analysis-output', `<div class="text-danger">${escapeHtml(error.message)}</div>`);
  }
}

async function runRisk(documentId) {
  try {
    setHTML('analysis-output', '<div class="text-muted">Analyzing document risk...</div>');
    
    const data = await api('/api/risk/analyze', {
      method: 'POST',
      body: JSON.stringify({ document_id: documentId }),
    });
    
    const scoreClass = data.risk_score <= 3 ? 'badge-low' : data.risk_score <= 6 ? 'badge-medium' : 'badge-high';
    
    setHTML(
      'analysis-output',
      `
        <div class="analysis-card glass-card">
          <div class="analysis-header">
            <h3 class="analysis-title">Risk Analysis</h3>
            <span class="badge badge-score ${scoreClass}">Score: ${data.risk_score}/10</span>
          </div>
          <p class="analysis-content">${escapeHtml(data.summary)}</p>
          <ul class="analysis-list">
            ${data.findings.map((item) => `<li>${escapeHtml(item)}</li>`).join('')}
          </ul>
        </div>
      `
    );
  } catch (error) {
    setHTML('analysis-output', `<div class="text-danger">${escapeHtml(error.message)}</div>`);
  }
}

async function loadChatDocumentOptions() {
  const data = await api('/api/documents');
  state.documents = data.documents;
  
  const select = byId('chat-document-id');
  if (select) {
    // Keep the "no document" option and add documents
    select.innerHTML = '<option value="">No document - Ask about Indian law</option>' + 
      data.documents.map((doc) => `<option value="${doc.id}">${escapeHtml(doc.filename)}</option>`).join('');
    
    const params = new URLSearchParams(window.location.search);
    const documentId = params.get('documentId');
    if (documentId) {
      state.selectedDocumentId = Number(documentId);
      select.value = documentId;
    }
  }
}

function appendMessage(role, text) {
  const container = byId('chat-messages');
  if (!container) {
    return;
  }
  appendChatbotMessage(container, role, text);
}

function appendChatbotMessage(container, role, text) {
  if (!container) return;
  
  // Clear empty state if present
  const emptyState = container.querySelector('.chatbot-empty');
  if (emptyState) {
    emptyState.remove();
  }
  
  const div = document.createElement('div');
  div.className = `chatbot-message chatbot-message-${role}`;
  
  if (role === 'user') {
    div.innerHTML = `
      <div class="chatbot-bubble chatbot-bubble-user">
        <div class="chatbot-text">${escapeHtml(text)}</div>
      </div>
    `;
  } else {
    div.innerHTML = `
      <div class="chatbot-bubble chatbot-bubble-assistant">
        <div class="chatbot-text chatbot-markdown">${renderMarkdown(text)}</div>
      </div>
    `;
  }
  
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

async function loadChatHistory(documentId) {
  try {
    const data = await api(`/api/chat-history/${documentId}`);
    const container = byId('chat-messages');
    if (!container) {
      return;
    }
    if (!data.messages.length) {
      container.innerHTML = '<div class="chatbot-empty">No conversation history yet. Ask a question to get started.</div>';
      return;
    }
    // Render messages in chatbot style (reverse order since API returns DESC)
    const reversedMessages = [...data.messages].reverse();
    container.innerHTML = reversedMessages
      .map(
        (message) => `
          <div class="chatbot-message chatbot-message-user">
            <div class="chatbot-bubble chatbot-bubble-user">
              <div class="chatbot-text">${escapeHtml(message.question)}</div>
            </div>
          </div>
          <div class="chatbot-message chatbot-message-assistant">
            <div class="chatbot-bubble chatbot-bubble-assistant">
              <div class="chatbot-text chatbot-markdown">${renderMarkdown(message.answer)}</div>
            </div>
          </div>
        `
      )
      .join('');
    container.scrollTop = container.scrollHeight;
  } catch (error) {
    console.error('Failed to load chat history:', error);
  }
}

function renderSourceContext(source, index) {
  const metadata = source.metadata || {};
  let locationInfo = '';
  
  if (metadata.page_number) {
    locationInfo += `<span class="context-meta">Page ${metadata.page_number}</span>`;
  }
  if (metadata.section_heading) {
    locationInfo += `<span class="context-meta">${escapeHtml(metadata.section_heading)}</span>`;
  }
  if (metadata.clause_number) {
    locationInfo += `<span class="context-meta">Clause ${escapeHtml(metadata.clause_number)}</span>`;
  }
  
  return `
    <div class="context-item">
      <div class="context-header">
        <div class="context-label">Document Excerpt ${index + 1}</div>
        ${locationInfo ? `<div class="context-location">${locationInfo}</div>` : ''}
      </div>
      <div class="context-text">${escapeHtml(source.text)}</div>
    </div>
  `;
}

function renderLawReference(ref, index, isExact = false) {
  const section = ref.section || '';
  const act = ref.act || ref.act_short || '';
  const title = ref.title || '';
  const description = ref.description || '';
  const punishment = ref.punishment || '';
  const newLaw = ref.new_law;
  const oldLaw = ref.old_law;
  
  let mappingInfo = '';
  if (newLaw) {
    mappingInfo = `<div class="law-mapping">➜ New Law: Section ${escapeHtml(newLaw.section)} of ${escapeHtml(newLaw.act)}</div>`;
  } else if (oldLaw) {
    mappingInfo = `<div class="law-mapping">← Old Law: Section ${escapeHtml(oldLaw.section)} of ${escapeHtml(oldLaw.act)}</div>`;
  }
  
  return `
    <div class="context-item law-reference ${isExact ? 'exact-match' : ''}">
      <div class="context-header">
        <div class="context-label">
          <span class="law-badge">${isExact ? '⚖️ Exact Match' : '📚 Related Law'}</span>
        </div>
      </div>
      <div class="law-section-title">Section ${escapeHtml(section)} of ${escapeHtml(act)}</div>
      ${title ? `<div class="law-title">${escapeHtml(title)}</div>` : ''}
      ${description ? `<div class="context-text">${escapeHtml(description)}</div>` : ''}
      ${punishment ? `<div class="law-punishment"><strong>Punishment:</strong> ${escapeHtml(punishment)}</div>` : ''}
      ${mappingInfo}
    </div>
  `;
}

function renderContextPanel(data) {
  const parts = [];
  
  // Document sources
  if (data.sources && data.sources.length) {
    parts.push('<div class="context-section"><h4 class="context-section-title">📄 Document Sources</h4>');
    parts.push(data.sources.map((source, index) => renderSourceContext(source, index)).join(''));
    parts.push('</div>');
  }
  
  // Law references
  const lawRefs = data.law_references || {};
  const sectionLookups = lawRefs.section_lookups || [];
  const semanticResults = lawRefs.semantic_results || [];
  
  if (sectionLookups.length || semanticResults.length) {
    parts.push('<div class="context-section"><h4 class="context-section-title">⚖️ Indian Law References</h4>');
    
    // Exact section matches first
    sectionLookups.forEach((ref, index) => {
      parts.push(renderLawReference(ref, index, true));
    });
    
    // Related semantic results
    semanticResults.forEach((ref, index) => {
      parts.push(renderLawReference(ref, index, false));
    });
    
    parts.push('</div>');
  }
  
  // Query type indicator
  if (data.query_type) {
    const typeLabels = {
      'law_only': '🔍 Indian Law Query',
      'document_only': '📄 Document Query',
      'document_plus_law': '📄⚖️ Combined Query',
    };
    parts.push(`<div class="query-type-badge">${typeLabels[data.query_type] || data.query_type}</div>`);
  }
  
  if (parts.length === 0) {
    return `
      <div class="context-empty">
        <svg class="context-empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
        </svg>
        <p>Source excerpts will appear here after you ask a question</p>
      </div>
    `;
  }
  
  return parts.join('');
}

async function handleLandingChat(event) {
  event.preventDefault();
  event.stopPropagation();
  
  const landingQuestionInput = byId('landing-question');
  const landingFileUpload = byId('landing-file-upload');
  const landingFileName = byId('landing-file-name');
  const landingChatMessages = byId('landing-chat-messages');
  const landingChatbot = byId('landing-chatbot');
  const statusId = 'landing-chat-status';
  
  const question = landingQuestionInput?.value?.trim();
  const file = landingFileUpload?.files?.[0];
  
  if (!question) {
    return;
  }
  
  // Mark chatbot as having messages (hides suggestions, shows messages area)
  if (landingChatbot) {
    landingChatbot.classList.add('has-messages');
  }
  
  // Add user message
  appendChatbotMessage(landingChatMessages, 'user', question);
  
  // Clear input immediately
  if (landingQuestionInput) landingQuestionInput.value = '';
  
  // If there's a file, upload it first
  let documentId = null;
  if (file) {
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      showStatus(statusId, `Uploading ${file.name}...`, 'loading');
      const result = await api('/api/documents/upload', {
        method: 'POST',
        body: formData,
      });
      documentId = result.document.id;
      if (result.document.upload_status === 'processing') {
        showStatus(statusId, `Processing ${file.name}...`, 'loading');
        await pollDocumentReady(documentId);
      }
      // Clear file input
      if (landingFileUpload) landingFileUpload.value = '';
      if (landingFileName) landingFileName.textContent = '';
    } catch (error) {
      showStatus(statusId, 'Upload failed: ' + error.message, 'error');
      return;
    }
  }
  
  // Now ask the question with streaming
  try {
    showStatus(statusId, 'Thinking...', 'loading');
    
    const streaming = appendStreamingMessage(landingChatMessages);
    const endpoint = documentId ? '/api/chat/stream' : '/api/law/ask/stream';
    const body = documentId ? { document_id: documentId, question } : { question };
    
    let landingFinalized = false;
    await streamChatFetch(
      endpoint,
      body,
      (token) => streaming.appendToken(token),
      () => {
        streaming.finalize();
        landingFinalized = true;
        hideStatus(statusId);
      }
    );
    if (!landingFinalized) {
      streaming.finalize();
      hideStatus(statusId);
    }
  } catch (error) {
    showStatus(statusId, error.message, 'error');
  }
}

async function handleDashboardChat(event) {
  event.preventDefault();
  event.stopPropagation();
  
  const dashboardQuestionInput = byId('dashboard-question');
  const dashboardFileUpload = byId('dashboard-file-upload');
  const dashboardFileName = byId('dashboard-file-name');
  const dashboardChatMessages = byId('dashboard-chat-messages');
  const dashboardSuggestions = byId('dashboard-suggestions');
  const statusId = 'dashboard-chat-status';
  
  const question = dashboardQuestionInput?.value?.trim();
  const file = dashboardFileUpload?.files?.[0];
  
  if (!question) {
    return;
  }
  
  // Hide suggestions after first question
  if (dashboardSuggestions) dashboardSuggestions.style.display = 'none';
  
  // Add user message
  appendChatbotMessage(dashboardChatMessages, 'user', question);
  
  // Clear input immediately
  if (dashboardQuestionInput) dashboardQuestionInput.value = '';
  
  // If there's a file, upload it first
  let documentId = null;
  if (file) {
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      showStatus(statusId, `Uploading ${file.name}...`, 'loading');
      const result = await api('/api/documents/upload', {
        method: 'POST',
        body: formData,
      });
      documentId = result.document.id;
      if (result.document.upload_status === 'processing') {
        showStatus(statusId, `Processing ${file.name}...`, 'loading');
        await pollDocumentReady(documentId);
      }
      // Clear file input
      if (dashboardFileUpload) dashboardFileUpload.value = '';
      if (dashboardFileName) dashboardFileName.textContent = '';
    } catch (error) {
      showStatus(statusId, 'Upload failed: ' + error.message, 'error');
      return;
    }
  }
  
  // Now ask the question with streaming
  try {
    showStatus(statusId, 'Thinking...', 'loading');
    
    const streaming = appendStreamingMessage(dashboardChatMessages);
    const endpoint = documentId ? '/api/chat/stream' : '/api/law/ask/stream';
    const body = documentId ? { document_id: documentId, question } : { question };
    
    let dashFinalized = false;
    await streamChatFetch(
      endpoint,
      body,
      (token) => streaming.appendToken(token),
      () => {
        streaming.finalize();
        dashFinalized = true;
        hideStatus(statusId);
      }
    );
    if (!dashFinalized) {
      streaming.finalize();
      hideStatus(statusId);
    }
  } catch (error) {
    showStatus(statusId, error.message, 'error');
  }
}

async function handleChat(event) {
  event.preventDefault();
  const statusId = 'chat-status';
  
  try {
    const question = byId('chat-question').value.trim();
    const documentIdValue = byId('chat-document-id').value;
    const documentId = documentIdValue ? Number(documentIdValue) : null;
    const suggestions = byId('chat-suggestions');
    
    if (!question) {
      throw new Error('Please enter a question');
    }
    
    // Hide suggestions after first question
    if (suggestions) suggestions.style.display = 'none';
    
    appendMessage('user', question);
    byId('chat-question').value = '';
    
    showStatus(statusId, 'Thinking...', 'loading');
    
    const container = byId('chat-messages');
    const streaming = appendStreamingMessage(container);
    const endpoint = documentId ? '/api/chat/stream' : '/api/law/ask/stream';
    const body = documentId ? { document_id: documentId, question } : { question };
    
    let streamFinalized = false;
    const doneReceived = await streamChatFetch(
      endpoint,
      body,
      (token) => streaming.appendToken(token),
      (doneEvent) => {
        streaming.finalize();
        streamFinalized = true;
        setHTML('retrieved-context', renderContextPanel(doneEvent));
        hideStatus(statusId);
      }
    );
    // If stream ended without a 'done' event, still finalize the message
    if (!streamFinalized) {
      streaming.finalize();
      hideStatus(statusId);
    }
  } catch (error) {
    showStatus(statusId, error.message, 'error');
  }
}

async function handleChatUpload(event) {
  const file = event.target.files[0];
  if (!file) return;
  
  const statusId = 'chat-upload-status';
  const validTypes = ['.pdf', '.docx'];
  const ext = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));
  
  if (!validTypes.includes(ext)) {
    showStatus(statusId, 'Only PDF and DOCX files are supported', 'error');
    return;
  }
  
  try {
    showStatus(statusId, `Uploading ${file.name}...`, 'loading');
    
    const formData = new FormData();
    formData.append('file', file);
    
    const data = await api('/api/documents/upload', {
      method: 'POST',
      body: formData,
    });
    
    // Refresh document list and select the new document
    await loadChatDocumentOptions();
    const select = byId('chat-document-id');
    if (select && data.document.id) {
      select.value = String(data.document.id);
      state.selectedDocumentId = data.document.id;
    }
    
    // Clear the file input
    event.target.value = '';
    
    if (data.document.upload_status === 'processing') {
      showStatus(statusId, `Processing ${data.document.filename}...`, 'loading');
      await pollDocumentReady(data.document.id, statusId);
    }
    showStatus(statusId, `Ready: ${data.document.filename}`, 'success');
    setTimeout(() => hideStatus(statusId), 3000);
  } catch (error) {
    showStatus(statusId, error.message, 'error');
  }
}

async function handleGeneratorUpload(event) {
  const file = event.target.files[0];
  if (!file) return;
  
  const statusId = 'generator-upload-status';
  const validTypes = ['.pdf', '.docx'];
  const ext = file.name.toLowerCase().slice(file.name.lastIndexOf('.'));
  
  if (!validTypes.includes(ext)) {
    showStatus(statusId, 'Only PDF and DOCX files are supported', 'error');
    return;
  }
  
  try {
    showStatus(statusId, `Uploading ${file.name}...`, 'loading');
    
    const formData = new FormData();
    formData.append('file', file);
    
    const data = await api('/api/documents/upload', {
      method: 'POST',
      body: formData,
    });
    
    showStatus(statusId, `Uploaded ${data.document.filename} - You can now reference it in your description`, 'success');
    
    // Update the label to show uploaded file
    const label = document.querySelector('#generator-document-file + .form-file-label');
    if (label) {
      label.innerHTML = `
        <svg class="form-file-icon-sm" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="color: var(--success);">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
          <polyline points="14 2 14 8 20 8"></polyline>
          <polyline points="9 15 12 18 15 15"></polyline>
          <line x1="12" y1="12" x2="12" y2="18"></line>
        </svg>
        <span class="form-file-text-sm" style="color: var(--success);">${escapeHtml(file.name)} uploaded</span>
      `;
    }
    
    setTimeout(() => hideStatus(statusId), 5000);
  } catch (error) {
    showStatus(statusId, error.message, 'error');
  }
}

const DOCUMENT_TYPE_NAMES = {
  legal_notice: 'Legal Notice',
  complaint_letter: 'Complaint Letter',
  nda: 'Non-Disclosure Agreement',
  rental_agreement: 'Rental Agreement',
};

async function handleGenerator(event, forceGenerate = false) {
  event.preventDefault();
  const statusId = 'generator-status';
  
  try {
    showStatus(statusId, 'Analyzing your request and generating document...', 'loading');
    
    const payload = {
      template_type: byId('template-type').value,
      name: byId('gen-name').value.trim(),
      address: byId('gen-address').value.trim(),
      issue_description: byId('gen-issue').value.trim(),
      date: byId('gen-date').value,
      force_generate: forceGenerate,
    };
    
    if (!payload.name || !payload.address || !payload.issue_description || !payload.date) {
      throw new Error('Please fill in all fields');
    }
    
    const data = await api('/api/generate-document', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    
    if (data.status === 'mismatch') {
      showStatus(statusId, '', 'warning');
      const suggestedName = DOCUMENT_TYPE_NAMES[data.suggested_type] || data.suggested_type;
      setHTML(
        'generator-preview',
        `<div class="validation-warning">
          <div class="warning-icon">⚠️</div>
          <h3>Document Type Mismatch Detected</h3>
          <p><strong>Issue:</strong> ${escapeHtml(data.mismatch_reason || data.message)}</p>
          <p><strong>Suggested document type:</strong> ${escapeHtml(suggestedName)}</p>
          <div class="warning-actions">
            <button class="btn btn-primary" type="button" onclick="switchToSuggestedType('${escapeHtml(data.suggested_type)}')">Switch to ${escapeHtml(suggestedName)}</button>
            <button class="btn btn-secondary" type="button" onclick="forceGenerateDocument()">Generate Anyway</button>
          </div>
        </div>`
      );
      setHTML('generator-download', '');
      return;
    }
    
    if (data.status === 'needs_info') {
      showStatus(statusId, '', 'warning');
      const missingItems = data.missing_info || [];
      setHTML(
        'generator-preview',
        `<div class="validation-warning">
          <div class="warning-icon">ℹ️</div>
          <h3>More Information Needed</h3>
          <p>${escapeHtml(data.message)}</p>
          ${missingItems.length ? `<ul class="missing-info-list">${missingItems.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>` : ''}
          <p>Please update your description with the required details and try again.</p>
        </div>`
      );
      setHTML('generator-download', '');
      return;
    }
    
    showStatus(statusId, 'Document generated successfully!', 'success');
    
    const previewContent = data.preview || data.content || 'Document generated but preview not available.';
    const previewEl = byId('generator-preview');
    if (previewEl) {
      previewEl.style.whiteSpace = 'pre-wrap';
      previewEl.textContent = previewContent;
    }
    
    if (data.download_url) {
      setHTML(
        'generator-download',
        `<a class="btn btn-primary" href="${escapeHtml(data.download_url)}" target="_blank">Download PDF</a>`
      );
    }
  } catch (error) {
    showStatus(statusId, error.message, 'error');
  }
}

function switchToSuggestedType(suggestedType) {
  const select = byId('template-type');
  if (select && suggestedType) {
    select.value = suggestedType;
    showStatus('generator-status', `Switched to ${DOCUMENT_TYPE_NAMES[suggestedType] || suggestedType}. Click "Generate Document" to proceed.`, 'success');
    setHTML('generator-preview', 'Your generated document will appear here after you fill out the form and click "Generate Document".');
    setHTML('generator-download', '');
  }
}

function forceGenerateDocument() {
  const form = byId('generator-form');
  if (form) {
    const fakeEvent = { preventDefault: () => {} };
    handleGenerator(fakeEvent, true);
  }
}

async function bootstrap() {
  const page = document.body.dataset.page;
  try {
    // Authentication disabled: always hydrate guest user
    await hydrateUser();
    
    if (page === 'dashboard') {
      await loadDocuments();
    }
    if (page === 'chat') {
      await loadChatDocumentOptions();
    }
  } catch (error) {
    console.error(error);
  }
}

window.addEventListener('DOMContentLoaded', () => {
  bootstrap();
  const signupForm = byId('signup-form');
  if (signupForm) signupForm.addEventListener('submit', (event) => handleSignup(event).catch((error) => alert(error.message)));
  const loginForm = byId('login-form');
  if (loginForm) loginForm.addEventListener('submit', (event) => handleLogin(event).catch((error) => alert(error.message)));
  const uploadForm = byId('upload-form');
  if (uploadForm) uploadForm.addEventListener('submit', (event) => handleUpload(event).catch((error) => alert(error.message)));
  
  // File input change handler to show selected filename
  const fileInput = byId('document-file');
  if (fileInput) {
    fileInput.addEventListener('change', (event) => {
      const file = event.target.files[0];
      const label = document.querySelector('.form-file-label');
      if (file && label) {
        label.innerHTML = `
          <svg class="form-file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" style="color: var(--accent-purple);">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
          </svg>
          <span class="form-file-text" style="color: var(--text-primary); font-weight: 600;">${escapeHtml(file.name)}</span>
          <span class="form-file-hint">${(file.size / 1024).toFixed(1)} KB - Click to change</span>
        `;
      }
    });
  }
  const chatForm = byId('chat-form');
  if (chatForm) chatForm.addEventListener('submit', (event) => handleChat(event).catch((error) => alert(error.message)));
  
  // Chat page document upload handler
  const chatFileInput = byId('chat-document-file');
  if (chatFileInput) {
    chatFileInput.addEventListener('change', (event) => handleChatUpload(event).catch((error) => alert(error.message)));
  }
  const generatorForm = byId('generator-form');
  if (generatorForm) generatorForm.addEventListener('submit', (event) => handleGenerator(event).catch((error) => alert(error.message)));
  
  // Dashboard ask form - handle inline (no redirect)
  const dashboardAskFormEarly = byId('dashboard-ask-form');
  if (dashboardAskFormEarly) {
    dashboardAskFormEarly.addEventListener('submit', (event) => handleDashboardChat(event).catch((error) => alert(error.message)));
  }
  
  // Generator page document upload handler
  const generatorFileInput = byId('generator-document-file');
  if (generatorFileInput) {
    generatorFileInput.addEventListener('change', (event) => handleGeneratorUpload(event).catch((error) => alert(error.message)));
  }
  const logoutButton = byId('logout-button');
  if (logoutButton) logoutButton.addEventListener('click', () => handleLogout().catch((error) => alert(error.message)));
  const chatSelect = byId('chat-document-id');
  if (chatSelect) chatSelect.addEventListener('change', (event) => loadChatHistory(Number(event.target.value)).catch((error) => alert(error.message)));
  
  const clearChatBtn = byId('clear-chat-btn');
  if (clearChatBtn) {
    clearChatBtn.addEventListener('click', () => {
      const select = byId('chat-document-id');
      if (select && select.value) {
        clearChatHistory(Number(select.value)).catch((error) => alert(error.message));
      } else {
        alert('Please select a document first.');
      }
    });
  }
  const quickClauseButton = byId('quick-clause-button');
  if (quickClauseButton) quickClauseButton.addEventListener('click', () => {
    const firstDocument = state.documents[0];
    if (!firstDocument) {
      alert('Upload a document first.');
      return;
    }
    runClause(firstDocument.id).catch((error) => alert(error.message));
  });
  const quickRiskButton = byId('quick-risk-button');
  if (quickRiskButton) quickRiskButton.addEventListener('click', () => {
    const firstDocument = state.documents[0];
    if (!firstDocument) {
      alert('Upload a document first.');
      return;
    }
    runRisk(firstDocument.id).catch((error) => alert(error.message));
  });
  
  // Document type card selection for generator
  const docTypeCards = document.querySelectorAll('.doc-type-card');
  docTypeCards.forEach(card => {
    card.addEventListener('click', () => {
      docTypeCards.forEach(c => c.classList.remove('active'));
      card.classList.add('active');
      const templateType = card.dataset.type;
      const templateInput = byId('template-type');
      if (templateInput) {
        templateInput.value = templateType;
      }
    });
  });
  
  // Suggested prompts for chat (both .suggested-btn and .suggestion-chip with data-prompt)
  document.querySelectorAll('.suggested-btn, .suggestion-chip[data-prompt]').forEach(btn => {
    btn.addEventListener('click', () => {
      const prompt = btn.dataset.prompt;
      const questionInput = byId('chat-question');
      if (questionInput && prompt) {
        questionInput.value = prompt;
        questionInput.focus();
      }
    });
  });
  
  // Set default date to today for generator
  const dateInput = byId('gen-date');
  if (dateInput && !dateInput.value) {
    const today = new Date().toISOString().split('T')[0];
    dateInput.value = today;
  }
  
  // ===== NEW LANDING PAGE FUNCTIONALITY =====
  
  // Mobile menu toggle
  const mobileToggle = byId('nav-mobile-toggle');
  const navMenu = document.querySelector('.nav-menu');
  if (mobileToggle && navMenu) {
    mobileToggle.addEventListener('click', () => {
      navMenu.classList.toggle('active');
      mobileToggle.classList.toggle('active');
    });
  }
  
  // Navbar scroll effect
  const navbarFixed = document.querySelector('.navbar-fixed');
  if (navbarFixed) {
    window.addEventListener('scroll', () => {
      if (window.scrollY > 50) {
        navbarFixed.classList.add('scrolled');
      } else {
        navbarFixed.classList.remove('scrolled');
      }
    });
  }
  
  // Landing page auth button and section visibility based on login state
  const navAuthBtn = byId('nav-auth-btn');
  const navLogoutBtn = byId('nav-logout-btn');
  const authSection = byId('auth');
  if (navAuthBtn && navLogoutBtn) {
    hydrateUser().then(user => {
      if (user) {
        navAuthBtn.style.display = 'none';
        navLogoutBtn.style.display = 'flex';
        // Hide auth section when logged in
        if (authSection) authSection.style.display = 'none';
      } else {
        navAuthBtn.style.display = 'inline-flex';
        navLogoutBtn.style.display = 'none';
        // Show auth section when not logged in
        if (authSection) authSection.style.display = 'block';
      }
    });
    
    navLogoutBtn.addEventListener('click', async () => {
      try {
        await api('/api/auth/logout', { method: 'POST' });
      } catch (error) {
        console.error('Logout API error (ignored):', error);
      }
      clearSessionToken();
      state.user = null;
      navAuthBtn.style.display = 'inline-flex';
      navLogoutBtn.style.display = 'none';
      if (authSection) authSection.style.display = 'block';
      window.location.href = '/';
    });
  }
  
  // Landing file upload display
  const landingFileUpload = byId('landing-file-upload');
  const landingFileName = byId('landing-file-name');
  if (landingFileUpload && landingFileName) {
    landingFileUpload.addEventListener('change', () => {
      const file = landingFileUpload.files[0];
      if (file) {
        landingFileName.textContent = file.name;
      } else {
        landingFileName.textContent = '';
      }
    });
  }
  
  // Suggestion chips for landing ask bar
  const suggestionChips = document.querySelectorAll('.suggestion-chip');
  const landingQuestion = byId('landing-question');
  suggestionChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const query = chip.dataset.query;
      if (landingQuestion && query) {
        landingQuestion.value = query;
        landingQuestion.focus();
      }
    });
  });
  
  // Landing ask form submission - answer inline (no redirect)
  const landingAskForm = byId('landing-ask-form');
  if (landingAskForm) {
    landingAskForm.addEventListener('submit', (event) => handleLandingChat(event).catch((error) => alert(error.message)));
  }
  
  // ===== EXPANDABLE CHATBOT FUNCTIONALITY =====
  const landingChatbot = byId('landing-chatbot');
  const landingExpandTrigger = byId('landing-expand-trigger');
  const landingCollapseBtn = byId('landing-collapse-btn');
  const landingQuestionInput = byId('landing-question');
  
  // Expand chatbot when clicking on collapsed bar
  if (landingExpandTrigger && landingChatbot) {
    landingExpandTrigger.addEventListener('click', () => {
      landingChatbot.classList.add('expanded');
      landingChatbot.classList.remove('collapsed');
      // Focus the input after expanding
      setTimeout(() => {
        if (landingQuestionInput) landingQuestionInput.focus();
      }, 100);
    });
  }
  
  // Collapse chatbot when clicking X button
  if (landingCollapseBtn && landingChatbot) {
    landingCollapseBtn.addEventListener('click', () => {
      // Only collapse if no messages yet
      const hasMessages = landingChatbot.classList.contains('has-messages');
      if (!hasMessages) {
        landingChatbot.classList.remove('expanded');
        landingChatbot.classList.add('collapsed');
      }
    });
  }
  
  // Landing suggestion cards (new style)
  document.querySelectorAll('#landing-suggestions .suggestion-card').forEach(card => {
    card.addEventListener('click', () => {
      const query = card.dataset.query;
      if (landingQuestionInput && query) {
        landingQuestionInput.value = query;
        landingQuestionInput.focus();
      }
    });
  });
  
  // Landing file upload display
  const landingFileUploadInput = byId('landing-file-upload');
  const landingFileNameDisplay = byId('landing-file-name');
  if (landingFileUploadInput && landingFileNameDisplay) {
    landingFileUploadInput.addEventListener('change', () => {
      const file = landingFileUploadInput.files[0];
      if (file) {
        landingFileNameDisplay.textContent = file.name;
      } else {
        landingFileNameDisplay.textContent = '';
      }
    });
  }
  
  // Smooth scroll for anchor links
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
      const targetId = this.getAttribute('href');
      if (targetId && targetId !== '#') {
        const target = document.querySelector(targetId);
        if (target) {
          e.preventDefault();
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          // Close mobile menu if open
          if (navMenu) navMenu.classList.remove('active');
          if (mobileToggle) mobileToggle.classList.remove('active');
        }
      }
    });
  });
  
  // ===== DASHBOARD ASK BAR FUNCTIONALITY =====
  
  // Dashboard file upload display
  const dashboardFileUpload = byId('dashboard-file-upload');
  const dashboardFileName = byId('dashboard-file-name');
  if (dashboardFileUpload && dashboardFileName) {
    dashboardFileUpload.addEventListener('change', () => {
      const file = dashboardFileUpload.files[0];
      if (file) {
        dashboardFileName.textContent = file.name;
      } else {
        dashboardFileName.textContent = '';
      }
    });
  }
  
  // Dashboard suggestion chips (use data-query for dashboard)
  const dashboardQuestionInput = byId('dashboard-question');
  document.querySelectorAll('#dashboard-suggestions .suggestion-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const query = chip.dataset.query;
      if (dashboardQuestionInput && query) {
        dashboardQuestionInput.value = query;
        dashboardQuestionInput.focus();
      }
    });
  });
});
