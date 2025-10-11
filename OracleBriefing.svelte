<script lang="ts">
	import { onMount, type SvelteComponent } from 'svelte';
	import { slide } from 'svelte/transition';
	import { quintOut } from 'svelte/easing';

	// --- Props ---
	/** The current mission data for the operator */
	export let mission: {
		subject: string;
		activity?: string;
		difficulty?: number;
		comment?: string;
		priority?: string;
		operator: string;
	};

	/** Component to render as the icon, e.g., an SVG component */
	export let icon: typeof SvelteComponent;

	// --- Internal State ---
	let briefing: {
		message: string;
		tactical_focus: string[];
		performance_insight: string;
		completion_estimate: number;
	} | null = null;

	let error: string | null = null;
	let isLoading = true;
	let show = false;

	// --- Logic ---
	onMount(() => {
		const fetchBriefing = async () => {
			isLoading = true;
			error = null;
			try {
				// The component calls its own endpoint, defined in the same route or a global one.
				// For this example, we assume a /api/oracle endpoint exists.
				const response = await fetch('/api/oracle', {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify(mission)
				});

				if (!response.ok) {
					const errorData = await response.json();
					throw new Error(errorData.error || 'Failed to receive transmission from Oracle.');
				}

				briefing = await response.json();
			} catch (e: any) {
				error = e.message;
				console.error('Oracle Briefing Error:', e);
			} finally {
				isLoading = false;
			}
		};

		fetchBriefing();

		// Delay the appearance for a more dramatic effect
		const timer = setTimeout(() => (show = true), 500);
		return () => clearTimeout(timer);
	});
</script>

{#if show}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
		on:click={() => (show = false)}
		on:keydown
		transition:slide={{ duration: 300, easing: quintOut }}
	>
		<div
			class="w-full max-w-2xl rounded-2xl border border-slate-700 bg-slate-900/80 p-8 shadow-2xl shadow-blue-500/10"
			on:click|stopPropagation
		>
			{#if isLoading}
				<div class="text-center text-slate-400">
					<p>Recebendo transmissão do Oráculo...</p>
					<div class="mt-4 h-1 w-full rounded-full bg-slate-800 overflow-hidden">
						<div class="h-1 animate-pulse rounded-full bg-gradient-to-r from-blue-500 to-purple-500" />
					</div>
				</div>
			{:else if error}
				<div class="text-center text-red-400">
					<h3 class="text-lg font-bold">Falha na Transmissão</h3>
					<p>{error}</p>
				</div>
			{:else if briefing}
				<div class="flex flex-col gap-6">
					<div class="flex items-start gap-4">
						<div class="mt-1 flex-shrink-0 text-blue-400">
							<svelte:component this={icon} class="h-8 w-8" />
						</div>
						<div>
							<h2 class="text-xl font-bold text-slate-100">Oracle's Briefing: {mission.subject}</h2>
							<p class="mt-2 text-slate-300">{briefing.message}</p>
						</div>
					</div>

					<div>
						<h3 class="font-semibold uppercase tracking-wider text-blue-400">Foco Tático</h3>
						<ul class="mt-2 list-disc list-inside space-y-1 text-slate-300">
							{#each briefing.tactical_focus as point}
								<li>{point}</li>
							{/each}
						</ul>
					</div>

					<p class="border-l-4 border-purple-500 bg-slate-800/50 p-4 text-sm italic text-slate-400">
						<strong>Insight de Performance:</strong> {briefing.performance_insight}
					</p>
				</div>
			{/if}
		</div>
	</div>
{/if}