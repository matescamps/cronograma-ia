<script lang="ts">
	import { fade } from 'svelte/transition';

	type CompletedMission = {
		id: number;
		subject: string;
		difficulty: number; // 1-5
		completion: number; // 0-100
	};

	// Mock data for the "War Map"
	const completedMissions: CompletedMission[] = [
		{ id: 1, subject: 'Álgebra', difficulty: 2, completion: 100 },
		{ id: 2, subject: 'Química Org.', difficulty: 4, completion: 85 },
		{ id: 3, subject: 'História', difficulty: 1, completion: 100 },
		{ id: 4, subject: 'Física', difficulty: 5, completion: 60 },
		{ id: 5, subject: 'Geometria', difficulty: 3, completion: 95 },
		{ id: 6, subject: 'Biologia', difficulty: 2, completion: 100 },
		{ id: 7, subject: 'Redação', difficulty: 3, completion: 75 },
		{ id: 8, subject: 'Literatura', difficulty: 1, completion: 100 }
	];

	function getDifficultyColor(difficulty: number): string {
		if (difficulty <= 2) return 'bg-green-500/60'; // Easy
		if (difficulty <= 3) return 'bg-yellow-500/60'; // Medium
		return 'bg-red-500/60'; // Hard
	}
</script>

<div class="grid grid-cols-2 gap-2 p-1 overflow-y-auto h-full">
	{#each completedMissions as mission (mission.id)}
		<div
			class="relative rounded-md border border-slate-700/50 p-2 transition-all hover:bg-slate-700/50"
			title="{mission.subject} - {mission.completion}% Concluído"
			in:fade={{ duration: 200, delay: mission.id * 50 }}
		>
			<div class="absolute inset-0 rounded-md {getDifficultyColor(mission.difficulty)}" style="width: {mission.completion}%;" />
			<p class="relative truncate text-sm font-semibold text-slate-200">{mission.subject}</p>
		</div>
	{/each}
</div>