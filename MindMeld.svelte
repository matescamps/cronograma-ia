<script lang="ts">
	import { createEventDispatcher } from 'svelte';
	import { slide, fade } from 'svelte/transition';
	import { quintOut } from 'svelte/easing';

	export let data: {
		perspectives: string[];
		challenge_question: string;
	};

	const dispatch = createEventDispatcher();

	function close() {
		dispatch('close');
	}
</script>

<div
	class="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 backdrop-blur-md"
	on:click={close}
	on:keydown
	transition:fade={{ duration: 200 }}
>
	<div
		class="w-full max-w-3xl rounded-lg border-2 border-red-500/80 bg-slate-950 p-8 shadow-2xl shadow-red-500/20"
		on:click|stopPropagation
		transition:slide={{ duration: 400, easing: quintOut, y: 50 }}
	>
		<div class="flex flex-col gap-6">
			<div class="text-center">
				<h2 class="text-2xl font-bold uppercase tracking-widest text-red-400">
					//: MIND MELD INITIATED
				</h2>
				<p class="text-slate-400">Radical perspectives unlocked.</p>
			</div>

			<div class="space-y-4">
				<h3 class="text-lg font-semibold text-slate-200">New Perspectives:</h3>
				{#each data.perspectives as perspective, i}
					<div class="border-l-4 border-slate-700 pl-4">
						<p class="text-slate-300">{perspective}</p>
					</div>
				{/each}
			</div>

			<div class="mt-4 border-t-2 border-dashed border-slate-700 pt-6">
				<h3 class="text-lg font-semibold text-slate-200">Challenge Question:</h3>
				<p class="mt-2 text-lg italic text-amber-300">"{data.challenge_question}"</p>
			</div>

			<div class="mt-6 flex justify-center">
				<button
					on:click={close}
					class="rounded-md bg-red-600/80 px-6 py-2 font-bold text-white transition-colors hover:bg-red-500"
				>
					Re-engage
				</button>
			</div>
		</div>
	</div>
</div>