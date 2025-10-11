<script lang="ts">
	import { session } from '$lib/stores/session';
	import MindMeld from './MindMeld.svelte';

	// Mock data for the current mission. This will come from your data source.
	const mission = {
		subject: 'Math - Spatial Geometry',
		activity: 'Cone Volume Exercises',
		difficulty: 4,
		comment: 'confused with cone volume calculation',
		priority: 'High',
		operator: $session.operator?.name || 'Operator'
	};

	let mindMeldData: any = null;
	let mindMeldError: string | null = null;
	let isMindMeldLoading = false;

	async function handleMindMeld() {
		if (isMindMeldLoading) return;

		isMindMeldLoading = true;
		mindMeldError = null;
		mindMeldData = null;

		try {
			const response = await fetch('/api/mind-meld', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					subject: mission.subject,
					activity: mission.activity,
					comment: mission.comment
				})
			});

			if (!response.ok) {
				const errorData = await response.json();
				throw new Error(errorData.error || 'MIND MELD transmission failed.');
			}

			mindMeldData = await response.json();
		} catch (e: any) {
			mindMeldError = e.message;
			// Show error to user via a toast or other UI element
			console.error('MIND MELD Error:', e);
		} finally {
			isMindMeldLoading = false;
		}
	}
</script>

<div class="flex h-full flex-col items-center justify-center gap-6 text-center">
	<div class="flex flex-col gap-1">
		<p class="text-lg uppercase tracking-widest text-blue-400">{mission.subject}</p>
		<h3 class="text-3xl font-bold text-slate-100">{mission.activity}</h3>
	</div>

	<div class="flex items-center gap-4 text-slate-400">
		<span>Priority: <strong class="text-amber-400">{mission.priority}</strong></span>
		<span class="h-4 border-l border-slate-600" />
		<span>Last Difficulty: <strong class="text-amber-400">{mission.difficulty}/5</strong></span>
	</div>

	<div class="mt-6 flex flex-col items-center gap-4">
		<button
			class="w-64 rounded-lg bg-blue-600 px-8 py-4 text-xl font-bold text-white shadow-lg shadow-blue-500/20 transition-all hover:scale-105 hover:bg-blue-500"
		>
			Engage Immersion
		</button>

		<button
			on:click={handleMindMeld}
			class="relative mt-4 flex h-14 w-14 items-center justify-center rounded-full border-2 border-red-500/50 bg-red-900/50 text-red-400 transition-all hover:scale-110 hover:border-red-500 hover:bg-red-900 hover:text-white"
			aria-label="Mind Meld"
		>
			{#if !isMindMeldLoading}
				<span
					class="absolute inline-flex h-full w-full animate-ping rounded-full bg-red-400 opacity-75"
				/>
			{/if}
			<svg
				xmlns="http://www.w3.org/2000/svg"
				class="relative h-8 w-8"
				viewBox="0 0 24 24"
				fill="currentColor"
			>
				<path
					d="M12 2C6.486 2 2 6.486 2 12s4.486 10 10 10 10-4.486 10-10S17.514 2 12 2zm0 18c-4.411 0-8-3.589-8-8s3.589-8 8-8 8 3.589 8 8-3.589 8-8 8z"
				/>
				<path d="M12 11a.997.997 0 0 0-1 1v3a1 1 0 0 0 2 0v-3a.997.997 0 0 0-1-1zM11 8h2v2h-2z" />
			</svg>
		</button>
		<p class="text-xs text-slate-500">Struggling? Press for AI assistance.</p>
	</div>
</div>

{#if mindMeldData}
	<MindMeld data={mindMeldData} on:close={() => (mindMeldData = null)} />
{/if}