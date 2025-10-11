<script lang="ts">
	import OracleBriefing from '$lib/components/OracleBriefing.svelte';
	import BrainIcon from '$lib/components/BrainIcon.svelte';
	import CinematicPortal from '$lib/components/CinematicPortal.svelte';
	import TemporalHorizon from '$lib/components/TemporalHorizon.svelte';
	import ToastContainer from '$lib/components/ToastContainer.svelte';
	import { session } from '$lib/stores/session';
	import { afterUpdate } from 'svelte';

	let mission: object | null = null;
	let showBriefing = false;

	// Reactive statement: when the operator logs in, prepare the mission
	$: if ($session.isAuthenticated && $session.operator) {
		mission = {
			subject: 'Math - Spatial Geometry',
			activity: 'Cone Volume Exercises',
			difficulty: 4,
			comment: 'confused with cone volume calculation',
			priority: 'High',
			operator: $session.operator.name
		};
	}

	// After the operator is set and the component updates, show the briefing
	afterUpdate(() => {
		if ($session.isAuthenticated && !showBriefing) {
			showBriefing = true;
		}
	});
</script>

<div class="h-screen w-screen bg-slate-950 text-slate-100 flex items-center justify-center">
	<ToastContainer />
	{#if !$session.isAuthenticated}
		<CinematicPortal />
	{:else}
		<TemporalHorizon />
		{#if showBriefing && mission}
			<OracleBriefing {mission} icon={BrainIcon} />
		{/if}
	{/if}
</div>