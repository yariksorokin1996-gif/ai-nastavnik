import { useState, useEffect, useCallback } from 'react';
import { fetchUser, type UserData } from '../api';

export function useUser() {
  const [user, setUser] = useState<UserData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchUser()
      .then(setUser)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return { user, loading, error, setUser, retry: load };
}

export type UserState = ReturnType<typeof useUser>;
