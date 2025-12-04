"use client";

import Link from 'next/link';
import { useAuth } from '@/context/AuthContext';
import { ThemeToggle } from '@/components/ThemeToggle';

export const Navbar = () => {
    const { user, logout, isAuthenticated, loading } = useAuth();

    return (
        <nav className="bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700 px-4 py-2.5">
            <div className="container flex flex-wrap justify-between items-center mx-auto">
                <Link href="/" className="flex items-center">
                    <span className="self-center text-xl font-semibold whitespace-nowrap dark:text-white">Football AI</span>
                </Link>
                <div className="flex items-center gap-6">
                    <ul className="flex flex-row space-x-6 text-sm font-medium">
                        <li>
                            <Link href="/" className="text-gray-700 dark:text-gray-300 hover:text-blue-600">
                                Live Matches
                            </Link>
                        </li>
                        <li>
                            <Link href="/teams" className="text-gray-700 dark:text-gray-300 hover:text-blue-600">
                                Teams
                            </Link>
                        </li>
                        <li>
                            <Link href="/search" className="text-gray-700 dark:text-gray-300 hover:text-blue-600">
                                Search
                            </Link>
                        </li>
                        <li>
                            <Link href="/compare" className="text-gray-700 dark:text-gray-300 hover:text-blue-600">
                                Compare
                            </Link>
                        </li>
                        {isAuthenticated && (
                            <>
                                <li>
                                    <Link href="/fantasy" className="text-gray-700 dark:text-gray-300 hover:text-blue-600">
                                        Fantasy League
                                    </Link>
                                </li>
                                <li>
                                    <Link href="/profile" className="text-gray-700 dark:text-gray-300 hover:text-blue-600">
                                        Profile
                                    </Link>
                                </li>
                            </>
                        )}
                    </ul>
                    <div className="flex items-center gap-3">
                        <ThemeToggle />
                        {loading ? (
                            <span className="text-gray-500 text-sm">Loading...</span>
                        ) : isAuthenticated ? (
                            <>
                                <span className="text-gray-700 dark:text-gray-300 text-sm font-medium">
                                    {user?.username}
                                </span>
                                <button
                                    onClick={logout}
                                    className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded hover:bg-red-700 transition"
                                >
                                    Logout
                                </button>
                            </>
                        ) : (
                            <>
                                <Link
                                    href="/login"
                                    className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-blue-600"
                                >
                                    Login
                                </Link>
                                <Link
                                    href="/register"
                                    className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded hover:bg-blue-700 transition"
                                >
                                    Register
                                </Link>
                            </>
                        )}
                    </div>
                </div>
            </div>
        </nav>
    );
};
