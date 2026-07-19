import { useRef, useEffect } from 'react';

export function useAutoScroll(deps = []) {
    const ref = useRef(null);

    useEffect(() => {
        const node = ref.current;
        if (!node) return;

        if (typeof node.scrollTo === 'function') {
            node.scrollTo({
                top: node.scrollHeight,
                behavior: 'smooth',
            });
            return;
        }

        if (typeof node.scrollTop === 'number') {
            node.scrollTop = node.scrollHeight;
        }
    }, deps);

    return ref;
}