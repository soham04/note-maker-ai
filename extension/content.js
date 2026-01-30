// Helper to wait for element
function waitForElement(selector) {
    return new Promise((resolve) => {
        if (document.querySelector(selector)) {
            return resolve(document.querySelector(selector));
        }

        const observer = new MutationObserver((mutations) => {
            if (document.querySelector(selector)) {
                observer.disconnect();
                resolve(document.querySelector(selector));
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true,
        });
    });
}

function getVideoId() {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('v');
}

// Auth State Logic
async function checkAuth() {
    try {
        const response = await fetch('http://localhost:8000/auth/status', {
            credentials: 'include'
        });
        if (response.ok) {
            return await response.json();
        }
        return null;
    } catch (e) {
        return null;
    }
}

// UI Creation
function createButton(initialState = 'LOGIN', userEmail = null) {
    const button = document.createElement('button');
    button.className = 'yt-notes-button';
    if (userEmail) {
        button.dataset.userEmail = userEmail;
    }

    updateButtonState(button, initialState);

    button.addEventListener('click', async () => {
        const currentState = button.dataset.state;

        if (currentState === 'LOGIN') {
            // Start Auth Flow
            window.open('http://localhost:8000/auth/google', 'loginPopup', 'width=600,height=700');
            button.textContent = 'Waiting for Login...';
            button.disabled = true;
        } else if (currentState === 'READY') {
            // Generate Notes
            await handleGenerateNotes(button);
        }
    });

    return button;
}

function updateButtonState(button, state) {
    button.dataset.state = state;
    button.disabled = false;
    button.classList.remove('loading', 'error', 'success');

    if (state === 'LOGIN') {
        button.textContent = 'Login to Notes AI';
    } else if (state === 'READY') {
        const email = button.dataset.userEmail;
        button.textContent = email ? `Make Notes (${email})` : 'Make Notes';
    } else if (state === 'GENERATING') {
        button.textContent = 'Generating...';
        button.disabled = true;
        button.classList.add('loading');
    }
}


async function handleGenerateNotes(button) {
    const videoId = getVideoId();
    if (!videoId) {
        alert('Could not detect video ID');
        return;
    }

    updateButtonState(button, 'GENERATING');

    try {
        // 1. Start Generation
        const response = await fetch('http://localhost:8000/generate-notes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({
                videoUrl: window.location.href,
                videoId: videoId
            }),
        });

        if (response.status === 401) {
            updateButtonState(button, 'LOGIN');
            throw new Error('Unauthorized');
        }

        if (!response.ok) throw new Error('Network response was not ok');

        // 2. Listen for Events via Fetch Stream (for credentials support)
        await streamEvents(videoId, button);

    } catch (error) {
        console.error('Error generating notes:', error);
        handleError(error, button);
    }
}

async function streamEvents(videoId, button) {
    try {
        const response = await fetch(`http://localhost:8000/notes/${videoId}/events`, {
            credentials: 'include'
        });

        if (!response.ok) throw new Error('SSE Connection failed');

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        handleStatusUpdate(data.status, button, videoId);
                        if (['ready', 'failed'].includes(data.status)) {
                            return; // Stop stream
                        }
                    } catch (e) {
                        // ignore parse errors or keepalive
                    }
                }
            }
        }
    } catch (error) {
        throw error;
    }
}

function handleStatusUpdate(status, button, videoId) {
    if (status === 'ready') {
        button.classList.remove('loading');
        button.classList.add('success');
        button.textContent = 'Download Note';
        button.disabled = false;

        // Convert to download link
        const link = document.createElement('a');
        link.href = '#';

        link.onclick = (e) => {
            e.preventDefault();
            downloadNote(videoId);
        };

        link.className = 'yt-notes-button success';
        link.textContent = 'Download Note';
        button.replaceWith(link);
    } else if (status === 'failed') {
        button.classList.add('error');
        button.textContent = 'Generation Failed';
        button.classList.remove('loading');
    }
}

async function downloadNote(videoId) {
    try {
        const response = await fetch(`http://localhost:8000/notes/${videoId}/download`, {
            credentials: 'include'
        });
        if (!response.ok) throw new Error('Download failed');

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;

        // content-disposition header might have filename
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = 'note.md';
        if (contentDisposition && contentDisposition.includes('filename=')) {
            filename = contentDisposition.split('filename=')[1].replace(/"/g, '');
        }

        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
    } catch (e) {
        alert('Failed to download note');
    }
}

function handleError(error, button) {
    if (error.message === 'Unauthorized') {
        alert('Session expired. Please login again.');
        updateButtonState(button, 'LOGIN');
    } else {
        button.classList.add('error');
        button.textContent = 'Error (Try Again)';
        button.classList.remove('loading');
        button.disabled = false;
        setTimeout(() => {
            checkAuth().then(isAuth => {
                updateButtonState(button, isAuth ? 'READY' : 'LOGIN');
            });
        }, 3000);
    }
}
let isInjecting = false;

async function injectButton() {
    // Check if we are on a video page
    if (!window.location.pathname.startsWith('/watch')) return;

    // Prevent concurrent injections
    if (isInjecting) return;
    isInjecting = true;

    try {
        // Double check existence before proceeding expensive async ops
        if (document.querySelector('.yt-notes-button')) return;

        const actionsContainer = await waitForElement('ytd-watch-metadata #top-level-buttons-computed');

        // Check again after await, specific to container
        if (!actionsContainer || actionsContainer.querySelector('.yt-notes-button')) return;

        // Also check if we already marked this container
        if (actionsContainer.dataset.notesButtonInjected === 'true') return;

        const authData = await checkAuth();
        const isAuth = !!authData;
        const initialState = isAuth ? 'READY' : 'LOGIN';
        const button = createButton(initialState, authData?.user);

        actionsContainer.insertBefore(button, actionsContainer.firstChild);
        actionsContainer.dataset.notesButtonInjected = 'true';

    } finally {
        isInjecting = false;
    }
}

// Auth Listener
window.addEventListener('message', async (event) => {
    // Basic security check - in prod we might want to check origin more strictly
    // but localhost callback is fine for now
    if (event.data && event.data.type === 'AUTH_SUCCESS') {
        // Update any existing buttons
        const button = document.querySelector('.yt-notes-button');
        if (button) {
            updateButtonState(button, 'READY');
        } else {
            // Or ensure state is reflected if re-injecting
        }
    }
});

// Observe for page navigations (SPA)
let lastUrl = location.href;
new MutationObserver(() => {
    const url = location.href;
    if (url !== lastUrl) {
        lastUrl = url;
        injectButton();
    }

    if (window.location.pathname.startsWith('/watch') && !document.querySelector('.yt-notes-button')) {
        injectButton();
    }
}).observe(document, { subtree: true, childList: true });

// Initial run
injectButton();
