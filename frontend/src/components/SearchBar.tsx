"use client";

import { useState, useEffect } from 'react';
import { Search, X, Loader2 } from 'lucide-react';

interface SearchBarProps {
    onSearch: (query: string) => void;
    placeholder?: string;
    loading?: boolean;
}

export const SearchBar = ({
    onSearch,
    placeholder = "Search teams and players...",
    loading = false
}: SearchBarProps) => {
    const [query, setQuery] = useState('');
    const [debouncedQuery, setDebouncedQuery] = useState('');

    // Debounce search query
    useEffect(() => {
        const timer = setTimeout(() => {
            setDebouncedQuery(query);
        }, 300);

        return () => clearTimeout(timer);
    }, [query]);

    // Call onSearch when debounced query changes
    useEffect(() => {
        if (debouncedQuery.trim()) {
            onSearch(debouncedQuery);
        }
    }, [debouncedQuery, onSearch]);

    const handleClear = () => {
        setQuery('');
        setDebouncedQuery('');
    };

    return (
        <div className="relative w-full max-w-3xl mx-auto">
            <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                    {loading ? (
                        <Loader2 className="w-5 h-5 text-gray-400 animate-spin" />
                    ) : (
                        <Search className="w-5 h-5 text-gray-400" />
                    )}
                </div>

                <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder={placeholder}
                    className="block w-full pl-12 pr-12 py-4 text-lg border-2 border-gray-300 dark:border-gray-600 rounded-full 
                     bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-400 
                     focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent
                     transition-all duration-300 shadow-lg hover:shadow-xl"
                />

                {query && (
                    <button
                        onClick={handleClear}
                        className="absolute inset-y-0 right-0 pr-4 flex items-center hover:bg-gray-100 dark:hover:bg-gray-700 rounded-r-full transition-colors"
                    >
                        <X className="w-5 h-5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200" />
                    </button>
                )}
            </div>

            {/* Search hint */}
            {!query && (
                <p className="mt-3 text-center text-sm text-gray-500 dark:text-gray-400">
                    Try searching for "Manchester", "Ronaldo", or your favorite team
                </p>
            )}
        </div>
    );
};
