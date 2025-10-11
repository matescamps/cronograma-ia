<script lang="ts">
	import { fly } from 'svelte/transition';
	import type { ToastType } from '$lib/stores/toasts';

	export let type: ToastType = 'default';
	export let message: string;

	const baseClass = 'flex items-center w-full max-w-xs p-4 space-x-4 rounded-lg shadow-lg text-slate-200';

	function getStyle(toastType: ToastType) {
		switch (toastType) {
			case 'taunt':
				return `${baseClass} bg-red-800/90 border border-red-600`;
			case 'encouragement':
				return `${baseClass} bg-green-800/90 border border-green-600`;
			case 'error':
				return `${baseClass} bg-red-900/90 border border-red-700`;
			case 'success':
				return `${baseClass} bg-green-900/90 border border-green-700`;
			default:
				return `${baseClass} bg-slate-800/90 border border-slate-700`;
		}
	}

	function getIcon(toastType: ToastType) {
		switch (toastType) {
			case 'taunt':
				return '🔥';
			case 'encouragement':
				return '✨';
			default:
				return 'ℹ️';
		}
	}
</script>

<div
	class={getStyle(type)}
	role="alert"
	transition:fly={{ x: 200, duration: 300 }}
>
	<div class="inline-flex items-center justify-center flex-shrink-0 w-8 h-8 rounded-lg">
		{getIcon(type)}
	</div>
	<div class="text-sm font-normal">{message}</div>
</div>