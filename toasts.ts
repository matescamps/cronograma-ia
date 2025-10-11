import { writable } from 'svelte/store';

export type ToastType = 'default' | 'success' | 'error' | 'taunt' | 'encouragement';

export type ToastMessage = {
	id: number;
	message: string;
	type: ToastType;
	duration: number;
};

const createToastStore = () => {
	const { subscribe, update } = writable<ToastMessage[]>([]);

	function add(message: string, type: ToastType = 'default', duration = 4000) {
		const id = Date.now();
		update((all) => [...all, { id, message, type, duration }]);
		setTimeout(() => remove(id), duration);
	}

	function remove(id: number) {
		update((all) => all.filter((t) => t.id !== id));
	}

	return { subscribe, add };
};

export const toasts = createToastStore();