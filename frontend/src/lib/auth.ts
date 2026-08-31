/**
 * 认证状态管理
 * 用 localStorage 保存登录后的 JWT，登录态变化时由 App 响应式渲染登录页或聊天区
 */

const TOKEN_KEY = "shopkeeper.token";
const USERNAME_KEY = "shopkeeper.username";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getUsername(): string | null {
  return localStorage.getItem(USERNAME_KEY);
}

export function setUsername(username: string) {
  localStorage.setItem(USERNAME_KEY, username);
}

export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
}

export function isLoggedIn(): boolean {
  return Boolean(getToken());
}
