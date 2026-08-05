/**
 * auth.js — JWT Authentication Helper
 * =====================================
 * Dùng chung cho tất cả các trang trong RiskDL.
 * 
 * Cách hoạt động:
 *  - Khi user đăng nhập (Django session), tự động gọi POST /api/token/ để lấy JWT.
 *  - Lưu token vào localStorage để dùng cho tất cả các API request.
 *  - Cung cấp hàm apiFetch() thay thế fetch() - tự động gắn Authorization header.
 *  - Nếu token hết hạn (401), tự động logout về trang login.
 */

const Auth = (() => {
    const TOKEN_KEY = 'riskdl_jwt_token';
    const USER_KEY  = 'riskdl_user';

    /** Lấy token từ localStorage */
    function getToken() {
        return localStorage.getItem(TOKEN_KEY);
    }

    /** Lưu token & thông tin user */
    function setToken(token, user) {
        localStorage.setItem(TOKEN_KEY, token);
        if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
    }

    /** Xoá token (logout) */
    function clearToken() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
    }

    /** Lấy thông tin user đã lưu */
    function getUser() {
        try {
            return JSON.parse(localStorage.getItem(USER_KEY) || 'null');
        } catch {
            return null;
        }
    }

    /**
     * Wrapper cho fetch() — tự động gắn JWT Authorization header.
     * Dùng thay thế fetch() ở mọi nơi trong code.
     * 
     * @param {string} url
     * @param {RequestInit} options
     * @returns {Promise<Response>}
     */
    async function apiFetch(url, options = {}) {
        const token = getToken();
        const headers = { ...(options.headers || {}) };

        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        // Với body là FormData thì không set Content-Type (browser tự xử lý)
        if (options.body && !(options.body instanceof FormData)) {
            if (!headers['Content-Type']) {
                headers['Content-Type'] = 'application/json';
            }
        }

        const res = await fetch(url, { ...options, headers });

        // Token hết hạn → logout về login
        if (res.status === 401) {
            const data = await res.json().catch(() => ({}));
            if (data.error && (data.error.includes('expired') || data.error.includes('Invalid token'))) {
                clearToken();
                window.location.href = '/login/';
                return res;
            }
        }

        return res;
    }

    /**
     * Khởi tạo JWT: nếu chưa có token hợp lệ trong localStorage,
     * thử lấy từ server qua endpoint đặc biệt dựa trên session hiện tại.
     * Được gọi tự động khi load trang.
     */
    async function init() {
        const existingToken = getToken();
        if (existingToken) {
            // Kiểm tra token còn hạn không (decode payload)
            try {
                const payload = JSON.parse(atob(existingToken.split('.')[1]));
                const now = Math.floor(Date.now() / 1000);
                if (payload.exp && payload.exp > now) {
                    return; // Token còn hợp lệ
                }
            } catch {
                // Token bị lỗi format, xoá đi
            }
            clearToken();
        }

        // Chưa có token → lấy từ session (user đã đăng nhập qua Django)
        try {
            const res = await fetch('/api/token/session/', {
                method: 'GET',
                credentials: 'same-origin',
            });
            if (res.ok) {
                const data = await res.json();
                if (data.token) {
                    setToken(data.token, data.user);
                }
            }
        } catch {
            // Không lấy được token, tiếp tục dùng session
        }
    }

    return { getToken, setToken, clearToken, getUser, apiFetch, init };
})();

// Tự động khởi tạo khi load trang
document.addEventListener('DOMContentLoaded', () => {
    Auth.init();
});

/**
 * Override global fetch để tự động gắn JWT cho mọi API call.
 * Chỉ áp dụng cho các request cùng origin (không ảnh hưởng external URLs).
 */
(function patchFetch() {
    const _originalFetch = window.fetch.bind(window);

    window.fetch = async function(url, options = {}) {
        // Chỉ inject token cho same-origin requests
        const isSameOrigin = typeof url === 'string' && (
            url.startsWith('/') || url.startsWith(window.location.origin)
        );

        if (isSameOrigin) {
            const token = Auth.getToken();
            if (token) {
                options = { ...options };
                options.headers = { ...(options.headers || {}) };
                // Không override nếu đã có Authorization header
                if (!options.headers['Authorization']) {
                    options.headers['Authorization'] = `Bearer ${token}`;
                }
                // Bypass CSRF cho JWT-authenticated requests
                options.headers['X-Requested-With'] = 'XMLHttpRequest';
            }
        }

        const res = await _originalFetch(url, options);

        // Token hết hạn → clear và redirect về login
        if (res.status === 401 && isSameOrigin) {
            const cloned = res.clone();
            try {
                const data = await cloned.json();
                if (data.error && (data.error.includes('expired') || data.error.includes('Invalid token'))) {
                    Auth.clearToken();
                    window.location.href = '/login/';
                }
            } catch { /* bỏ qua nếu không parse được JSON */ }
        }

        return res;
    };
})();

