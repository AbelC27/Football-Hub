"use client";

import { useState, useEffect, useRef } from "react";
import { Search, X, Check } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

interface Option {
    id: number;
    name: string;
    image_url?: string;
    subtitle?: string;
}

interface SearchableSelectProps {
    placeholder: string;
    onSearch: (query: string) => Promise<Option[]>;
    onSelect: (option: Option | null) => void;
    selectedOption: Option | null;
    label: string;
}

export const SearchableSelect = ({
    placeholder,
    onSearch,
    onSelect,
    selectedOption,
    label,
}: SearchableSelectProps) => {
    const [isOpen, setIsOpen] = useState(false);
    const [query, setQuery] = useState("");
    const [options, setOptions] = useState<Option[]>([]);
    const [loading, setLoading] = useState(false);
    const wrapperRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const handleClickOutside = (event: MouseEvent) => {
            if (wrapperRef.current && !wrapperRef.current.contains(event.target as Node)) {
                setIsOpen(false);
            }
        };
        document.addEventListener("mousedown", handleClickOutside);
        return () => document.removeEventListener("mousedown", handleClickOutside);
    }, []);

    useEffect(() => {
        const timer = setTimeout(() => {
            if (query.length >= 2) {
                setLoading(true);
                onSearch(query)
                    .then(setOptions)
                    .catch(console.error)
                    .finally(() => setLoading(false));
            }
        }, 300);
        return () => clearTimeout(timer);
    }, [query, onSearch]);

    return (
        <div className="w-full" ref={wrapperRef}>
            <label className="block text-sm font-medium text-neutral-400 mb-2">{label}</label>

            {selectedOption ? (
                <div className="relative p-4 bg-neutral-900 border border-neutral-800 rounded-xl flex items-center gap-4 group">
                    {selectedOption.image_url ? (
                        <img src={selectedOption.image_url} alt={selectedOption.name} className="w-10 h-10 object-contain" />
                    ) : (
                        <div className="w-10 h-10 bg-neutral-800 rounded-full flex items-center justify-center">
                            <span className="text-neutral-500 font-bold">{selectedOption.name[0]}</span>
                        </div>
                    )}
                    <div className="flex-1">
                        <div className="font-bold text-white">{selectedOption.name}</div>
                        {selectedOption.subtitle && (
                            <div className="text-xs text-neutral-500">{selectedOption.subtitle}</div>
                        )}
                    </div>
                    <button
                        onClick={() => {
                            onSelect(null);
                            setQuery("");
                        }}
                        className="p-2 hover:bg-neutral-800 rounded-full text-neutral-500 hover:text-red-500 transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>
            ) : (
                <div className="relative">
                    <div className="relative">
                        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-500" />
                        <input
                            type="text"
                            placeholder={placeholder}
                            value={query}
                            onChange={(e) => {
                                setQuery(e.target.value);
                                setIsOpen(true);
                            }}
                            onFocus={() => setIsOpen(true)}
                            className="w-full pl-12 pr-4 py-4 rounded-xl border border-neutral-800 bg-neutral-900/50 text-neutral-200 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 transition-all placeholder:text-neutral-600"
                        />
                    </div>

                    <AnimatePresence>
                        {isOpen && (query.length >= 2 || options.length > 0) && (
                            <motion.div
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: 10 }}
                                className="absolute z-50 w-full mt-2 bg-neutral-900 border border-neutral-800 rounded-xl shadow-2xl overflow-hidden max-h-64 overflow-y-auto"
                            >
                                {loading ? (
                                    <div className="p-4 text-center text-neutral-500">Searching...</div>
                                ) : options.length > 0 ? (
                                    options.map((option) => (
                                        <button
                                            key={option.id}
                                            onClick={() => {
                                                onSelect(option);
                                                setIsOpen(false);
                                            }}
                                            className="w-full p-3 flex items-center gap-3 hover:bg-neutral-800 transition-colors text-left border-b border-neutral-800 last:border-0"
                                        >
                                            {option.image_url ? (
                                                <img src={option.image_url} alt={option.name} className="w-8 h-8 object-contain" />
                                            ) : (
                                                <div className="w-8 h-8 bg-neutral-800 rounded-full flex items-center justify-center">
                                                    <span className="text-xs font-bold text-neutral-500">{option.name[0]}</span>
                                                </div>
                                            )}
                                            <div>
                                                <div className="font-medium text-neutral-200">{option.name}</div>
                                                {option.subtitle && (
                                                    <div className="text-xs text-neutral-500">{option.subtitle}</div>
                                                )}
                                            </div>
                                        </button>
                                    ))
                                ) : (
                                    <div className="p-4 text-center text-neutral-500">No results found</div>
                                )}
                            </motion.div>
                        )}
                    </AnimatePresence>
                </div>
            )}
        </div>
    );
};
