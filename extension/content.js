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
async function getToken() {
    return new Promise((resolve) => {
        chrome.storage.local.get(['yt_notes_jwt'], (result) => {
            resolve(result.yt_notes_jwt);
        });
    });
}

async function setToken(token) {
    return new Promise((resolve) => {
        chrome.storage.local.set({ yt_notes_jwt: token }, () => {
            resolve();
        });
    });
}

async function clearToken() {
    return new Promise((resolve) => {
        chrome.storage.local.remove(['yt_notes_jwt'], () => {
            resolve();
        });
    });
}

// UI Creation
function createButton(initialState = 'LOGIN') {
    const button = document.createElement('button');
    button.className = 'yt-notes-button';

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
        button.textContent = 'Make Notes';
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
        const token = await getToken();
        if (!token) {
            updateButtonState(button, 'LOGIN');
            return;
        }

        const response = await fetch('http://localhost:8000/generate-notes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                videoUrl: window.location.href,
                videoId: videoId
            }),
        });

        if (response.status === 401) {
            await clearToken();
            updateButtonState(button, 'LOGIN');
            throw new Error('Unauthorized');
        }

        if (!response.ok) throw new Error('Network response was not ok');

        const data = await response.json();

        if (data.driveUrl) {
            button.classList.remove('loading');
            button.classList.add('success');
            button.textContent = 'Open in Drive';
            button.disabled = false;

            // Replace with link to avoid event listener issues
            const link = document.createElement('a');
            link.href = data.driveUrl;
            link.className = 'yt-notes-button success';
            link.textContent = 'Open in Drive';
            link.target = '_blank';
            button.replaceWith(link);
        }
    } catch (error) {
        console.error('Error generating notes:', error);

        if (error.message === 'Unauthorized') {
            // Already handled state update above
            alert('Session expired. Please login again.');
        } else {
            button.classList.add('error');
            button.textContent = 'Error (Try Again)';
            button.classList.remove('loading');
            button.disabled = false;

            setTimeout(() => {

                // Just reset to READY if we think we are logged in, or LOGIN if not.
                // For simplicity, just reset to READY/LOGIN based on token presence
                getToken().then(t => {
                    updateButtonState(button, t ? 'READY' : 'LOGIN');
                });
            }, 8000);
        }
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

        const token = await getToken();
        const initialState = token ? 'READY' : 'LOGIN';
        const button = createButton(initialState);

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
    if (event.data && event.data.type === 'AUTH_SUCCESS' && event.data.token) {
        await setToken(event.data.token);

        // Update any existing buttons
        const button = document.querySelector('.yt-notes-button');
        if (button) {
            updateButtonState(button, 'READY');
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
