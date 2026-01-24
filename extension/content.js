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

function createButton() {
    const button = document.createElement('button');
    button.className = 'yt-notes-button';
    button.textContent = 'Make Notes';

    button.addEventListener('click', async () => {
        const videoId = getVideoId();
        if (!videoId) {
            alert('Could not detect video ID');
            return;
        }

        button.disabled = true;
        button.classList.add('loading');
        button.textContent = 'Generating...';

        try {
            const response = await fetch('http://localhost:3000/api/notes', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    videoUrl: window.location.href,
                    videoId: videoId
                }),
            });

            if (!response.ok) throw new Error('Network response was not ok');

            const data = await response.json();

            if (data.downloadUrl) {
                button.classList.remove('loading');
                button.classList.add('success');
                button.textContent = 'Download Notes';

                // Change button to be a link or just open the download
                const link = document.createElement('a');
                link.href = data.downloadUrl;
                link.className = 'yt-notes-button success';
                link.textContent = 'Download Notes';
                link.target = '_blank';
                button.replaceWith(link);
            }
        } catch (error) {
            console.error('Error generating notes:', error);
            button.classList.remove('loading');
            button.classList.add('error');
            button.textContent = 'Error (Try Again)';
            button.disabled = false;
            setTimeout(() => {
                button.classList.remove('error');
                button.textContent = 'Make Notes';
            }, 3000);
        }
    });

    return button;
}

async function injectButton() {
    // Check if we are on a video page
    if (!window.location.pathname.startsWith('/watch')) return;

    // Check if button already exists
    if (document.querySelector('.yt-notes-button')) return;

    // YouTube's DOM is complex. 
    // We'll try to insert next to the Subscribe button or in the top row Actions.
    // #top-row is where the Like/Share/Download buttons usually are.
    // #owner is where the channel name and subscribe button are.

    // Let's target the "actions" strip where Like/Share are. 
    // It usually has an ID like `actions` or `actions-inner` inside `#top-row`.
    // Using a broad selector to catch it.

    // Try to find the menu renderer
    const actionsContainer = await waitForElement('#top-row #actions');

    if (actionsContainer && !document.querySelector('.yt-notes-button')) {
        const button = createButton();
        // Insert at the beginning of actions
        actionsContainer.insertBefore(button, actionsContainer.firstChild);
    }
}

// Observe for page navigations (SPA)
let lastUrl = location.href;
new MutationObserver(() => {
    const url = location.href;
    if (url !== lastUrl) {
        lastUrl = url;
        injectButton(); // Re-run injection logic on URL change
    }

    // Also constantly check if button is missing (e.g. re-render)
    if (window.location.pathname.startsWith('/watch') && !document.querySelector('.yt-notes-button')) {
        injectButton();
    }
}).observe(document, { subtree: true, childList: true });

// Initial run
injectButton();
