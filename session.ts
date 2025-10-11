import { writable } from 'svelte/store';
import { browser } from '$app/environment';

export type Operator = {
	id: string;
	name: string;
	insignia: string;
};

type SessionState = {
	isAuthenticated: boolean;
	operator: Operator | null;
};

const SESSION_KEY = 'focus_os_session';

// Load initial state from localStorage only on the client side
const initialValue: SessionState = browser
	? JSON.parse(localStorage.getItem(SESSION_KEY) || 'null') || {
			isAuthenticated: false,
			operator: null
	  }
	: { isAuthenticated: false, operator: null };

function createSessionStore() {
	const { subscribe, set } = writable<SessionState>(initialValue);

	return {
		subscribe,
		login: (operator: Operator) => {
			const sessionState = { isAuthenticated: true, operator };
			if (browser) {
				localStorage.setItem(SESSION_KEY, JSON.stringify(sessionState));
			}
			set(sessionState);
		},
		logout: () => {
			if (browser) {
				localStorage.removeItem(SESSION_KEY);
			}
			set({ isAuthenticated: false, operator: null });
		}
	};
}

export const session = createSessionStore();