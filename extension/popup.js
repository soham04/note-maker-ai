const BASE_URL = 'http://localhost:8000';

document.addEventListener('DOMContentLoaded', async () => {
    const statusContainer = document.getElementById('status-container');
    const unauthView = document.getElementById('unauth-view');
    const authView = document.getElementById('auth-view');
    const loginBtn = document.getElementById('login-btn');
    const logoutBtn = document.getElementById('logout-btn');

    async function checkAuth() {
        try {
            const response = await fetch(`${BASE_URL}/auth/status`, {
                credentials: 'include'
            });
            if (response.ok) {
                const data = await response.json();
                return data;
            }
            return null;
        } catch (e) {
            console.error('Auth check failed', e);
            return null;
        }
    }

    async function updateUI() {
        statusContainer.textContent = 'Checking...';
        const user = await checkAuth();

        if (user) {
            statusContainer.textContent = `Logged in as ${user.user}`;
            unauthView.classList.add('hidden');
            authView.classList.remove('hidden');
        } else {
            statusContainer.textContent = 'Not logged in';
            unauthView.classList.remove('hidden');
            authView.classList.add('hidden');
        }
    }

    loginBtn.addEventListener('click', () => {
        window.open(`${BASE_URL}/auth/google`, 'loginPopup', 'width=600,height=700');
        // Poll for login success via window message or just simpler:
        // User closes popup, we can just re-check or user clicks extension again.
        // Or we can add a listener like in content.js if we want to be fancy.
        window.close(); // Close popup so user can see the login window clearly? Or keep it open?
        // Usually extension popups close when focus is lost anyway.
    });

    logoutBtn.addEventListener('click', async () => {
        try {
            await fetch(`${BASE_URL}/auth/logout`, {
                method: 'POST',
                credentials: 'include'
            });
            updateUI();
        } catch (e) {
            statusContainer.textContent = 'Logout failed';
        }
    });

    updateUI();
});
