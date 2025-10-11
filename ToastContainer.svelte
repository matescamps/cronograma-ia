<script lang="ts">
	import { toasts } from '$lib/stores/toasts';
	import Toast from './Toast.svelte';
</script>

<div class="fixed top-5 right-5 z-[100] flex flex-col gap-3">
	{#each $toasts as toast (toast.id)}
		<Toast
			type={toast.type}
			message={toast.message}
		/>
	{/each}
</div>