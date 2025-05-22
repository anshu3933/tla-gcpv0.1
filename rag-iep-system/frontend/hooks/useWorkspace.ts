export function useWorkspace() {
  async function getToken(): Promise<string> {
    const token = sessionStorage.getItem('authToken');
    return token || '';
  }
  return { getToken };
}
