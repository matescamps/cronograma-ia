import { writable } from 'svelte/store';

type UiState = {
	isImmersionMode: boolean;
};

function createUiStore() {
	const { subscribe, update } = writable<UiState>({ isImmersionMode: false });

	return { subscribe, toggleImmersion: () => update((state) => ({ ...state, isImmersionMode: !state.isImmersionMode })) };
}

export const ui = createUiStore();