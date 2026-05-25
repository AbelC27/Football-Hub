import React from 'react';

interface PredictionProps {
    homeProb: number;
    drawProb: number;
    awayProb: number;
}

export const PredictionBadge: React.FC<PredictionProps> = ({ homeProb, drawProb, awayProb }) => {
    // Normalize so the three probabilities always sum to exactly 100%
    const total = homeProb + drawProb + awayProb;
    const normHome = total > 0 ? (homeProb / total) * 100 : 0;
    const normDraw = total > 0 ? (drawProb / total) * 100 : 0;
    const normAway = total > 0 ? (awayProb / total) * 100 : 0;

    return (
        <div className="mt-2 p-2 bg-gray-100 dark:bg-gray-700 rounded">
            <div className="text-xs font-bold mb-1 text-center dark:text-gray-200">AI Prediction</div>
            <div className="flex justify-between text-xs">
                <div className="text-center">
                    <div className="font-semibold text-green-600 dark:text-green-400">{normHome.toFixed(2)}%</div>
                    <div className="dark:text-gray-300">Home</div>
                </div>
                <div className="text-center">
                    <div className="font-semibold text-gray-500 dark:text-gray-400">{normDraw.toFixed(2)}%</div>
                    <div className="dark:text-gray-300">Draw</div>
                </div>
                <div className="text-center">
                    <div className="font-semibold text-red-600 dark:text-red-400">{normAway.toFixed(2)}%</div>
                    <div className="dark:text-gray-300">Away</div>
                </div>
            </div>
        </div>
    );
};
