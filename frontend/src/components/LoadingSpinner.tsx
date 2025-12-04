'use client';

import React from 'react';

export const LoadingSpinner: React.FC = () => {
    return (
        <div className="flex items-center justify-center min-h-[400px]">
            <div className="relative">
                <div className="w-20 h-20 border-4 border-blue-200 dark:border-blue-900 rounded-full animate-pulse"></div>
                <div className="w-20 h-20 border-4 border-t-blue-600 border-r-transparent border-b-transparent border-l-transparent rounded-full animate-spin absolute top-0 left-0"></div>
                <div className="absolute inset-0 flex items-center justify-center">
                    <div className="w-8 h-8 bg-blue-600 rounded-full animate-ping opacity-75"></div>
                </div>
            </div>
        </div>
    );
};

export const MatchCardSkeleton: React.FC = () => {
    return (
        <div className="bg-white dark:bg-gray-800 rounded-xl p-6 border-2 border-gray-200 dark:border-gray-700 animate-pulse">
            <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/3 mb-4"></div>
            <div className="flex items-center justify-between gap-6">
                <div className="flex flex-col items-center flex-1">
                    <div className="w-20 h-20 bg-gray-200 dark:bg-gray-700 rounded-full mb-3"></div>
                    <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-24"></div>
                </div>
                <div className="flex flex-col items-center">
                    <div className="w-12 h-12 bg-gray-200 dark:bg-gray-700 rounded mb-2"></div>
                    <div className="w-8 h-8 bg-gray-200 dark:bg-gray-700 rounded-full mb-2"></div>
                    <div className="w-12 h-12 bg-gray-200 dark:bg-gray-700 rounded"></div>
                </div>
                <div className="flex flex-col items-center flex-1">
                    <div className="w-20 h-20 bg-gray-200 dark:bg-gray-700 rounded-full mb-3"></div>
                    <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-24"></div>
                </div>
            </div>
        </div>
    );
};
