<script lang="ts">
	import { session } from '$lib/stores/session';
	import { toasts } from '$lib/stores/toasts';
	import { onMount } from 'svelte';

	type AllyData = {
		name: string;
		status: 'ONLINE' | 'OFFLINE' | 'IN-MISSION';
		currentMission: string;
		streak: number;
	};

	let ally: AllyData | null = null;

	// Mock data for the two operators in the system
	const operatorsData = {
		Mateus: { name: 'Mateus', status: 'ONLINE', currentMission: 'Math', streak: 5 },
		Ana: { name: 'Ana', status: 'IN-MISSION', currentMission: 'Organic Chemistry', streak: 7 }
	};

	onMount(() => {
		// Determine who the ally is based on the logged-in operator
		const currentOperatorName = $session.operator?.name;
		if (currentOperatorName === 'Mateus') {
			ally = operatorsData.Ana;
		} else if (currentOperatorName === 'Ana') {
			ally = operatorsData.Mateus;
		}
	});

	function getStatusClass(status: AllyData['status']) {
		if (status === 'IN-MISSION') return 'text-yellow-400';
		if (status === 'ONLINE') return 'text-green-400';
		return 'text-slate-500';
	}
</script>

{#if ally}
	<div class="flex items-center gap-4">
		<div class="text-right">
			<p class="text-slate-400">
				ALLY: {ally.name} | STATUS:
				<span class="font-bold {getStatusClass(ally.status)}">{ally.status}</span>
			</p>
			<p class="text-sm text-slate-500">
				Current Mission: {ally.currentMission} | Streak: {ally.streak}
			</p>
		</div>
		<div class="flex flex-col gap-1">
			<button
				on:click={() => toasts.add(`Encouragement sent to ${ally?.name}!`, 'encouragement')}
				class="px-2 py-0.5 text-xs bg-green-600/50 hover:bg-green-600 rounded-md transition-colors"
				title="Send Encouragement"
			>
				✨
			</button>
			<button
				on:click={() => toasts.add(`Taunt sent to ${ally?.name}! Keep up!`, 'taunt')}
				class="px-2 py-0.5 text-xs bg-red-600/50 hover:bg-red-600 rounded-md transition-colors"
				title="Send Taunt"
			>
				🔥
			</button>
		</div>
	</div>
{/if}