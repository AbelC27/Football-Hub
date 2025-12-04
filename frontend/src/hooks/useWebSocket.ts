import { useEffect, useRef, useState } from 'react';

export const useWebSocket = (url: string) => {
    const [lastMessage, setLastMessage] = useState<any>(null);
    const ws = useRef<WebSocket | null>(null);

    useEffect(() => {
        ws.current = new WebSocket(url);

        ws.current.onopen = () => {
            console.log('WebSocket Connected');
        };

        ws.current.onmessage = (event) => {
            const message = JSON.parse(event.data);
            setLastMessage(message);
        };

        ws.current.onclose = () => {
            console.log('WebSocket Disconnected');
        };

        return () => {
            ws.current?.close();
        };
    }, [url]);

    return lastMessage;
};
