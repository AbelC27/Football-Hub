"use client";

import React, { createContext, useContext, useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { createClient } from '@/utils/supabase/client';

interface User {
    id: string; // Changed from number to string for Supabase UUID
    email: string;
    username: string;
    favorite_team_id?: number;
    favorite_player_id?: number;
}

interface AuthContextType {
    user: User | null;
    token: string | null;
    login: () => void;
    logout: () => Promise<void>;
    isAuthenticated: boolean;
    loading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [user, setUser] = useState<User | null>(null);
    const [token, setToken] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const router = useRouter();
    const supabase = createClient();

    useEffect(() => {
        const initializeAuth = async () => {
            const { data: { session } } = await supabase.auth.getSession();
            if (session) {
                setToken(session.access_token);
                await fetchUser(session.access_token);
            } else {
                setLoading(false);
            }
        };

        initializeAuth();

        const { data: { subscription } } = supabase.auth.onAuthStateChange(async (event, session) => {
            if (session) {
                setToken(session.access_token);
                await fetchUser(session.access_token);
            } else {
                setToken(null);
                setUser(null);
            }
        });

        return () => {
            subscription.unsubscribe();
        };
    }, []);

    const fetchUser = async (authToken: string) => {
        try {
            const response = await fetch('http://localhost:8000/api/v1/auth/me', {
                headers: {
                    'Authorization': `Bearer ${authToken}`
                }
            });

            if (response.ok) {
                const userData = await response.json();
                setUser(userData);
            } else {
                // Ignore silent failures if FastAPI fails to load the profile initially
                console.error("Failed to load user profile from backend.");
            }
        } catch (error) {
            console.error("Failed to fetch user", error);
        } finally {
            setLoading(false);
        }
    };

    const login = () => {
        // Redirection handled by individual forms
        router.push('/');
    };

    const logout = async () => {
        setLoading(true);
        await supabase.auth.signOut();
        setToken(null);
        setUser(null);
        router.push('/login');
        setLoading(false);
    };

    return (
        <AuthContext.Provider value={{ user, token, login, logout, isAuthenticated: !!user, loading }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (context === undefined) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};
