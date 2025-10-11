<script lang="ts">
	import { slide } from 'svelte/transition';

	type FutureMission = {
		id: number;
		subject: string;
		priority: 'Baixa' | 'Média' | 'Alta' | 'Crítica';
		reason: string; // AI's reasoning for scheduling this mission
	};

	// Mock data representing the AI's forecast
	const forecast: FutureMission[] = [
		{
			id: 1,
			subject: 'Química Orgânica',
			priority: 'Alta',
			reason: 'Média de conclusão abaixo do esperado.'
		},
		{ id: 2, subject: 'Física - Óptica', priority: 'Média', reason: 'Revisão agendada.' },
		{
			id: 3,
			subject: 'História do Brasil',
			priority: 'Crítica',
			reason: 'Alta prioridade no ENEM.'
		},
		{ id: 4, subject: 'Matemática - Logaritmos', priority: 'Média', reason: 'Revisão agendada.' }
	];

	function getPriorityClass(priority: FutureMission['priority']): string {
		switch (priority) {
			case 'Crítica':
				return 'border-red-500';
			case 'Alta':
				return 'border-amber-500';
			case 'Média':
				return 'border-blue-500';
			default:
				return 'border-slate-600';
		}
	}
</script>

<div class="flex h-full flex-col gap-3 overflow-y-auto p-1">
	{#each forecast as mission (mission.id)}
		<div
			class="flex flex-col rounded-md border-l-4 bg-slate-800/50 p-3 transition-all hover:bg-slate-800"
			class:list={getPriorityClass(mission.priority)}
			title={mission.reason}
			transition:slide={{ duration: 300, delay: mission.id * 75, axis: 'x' }}
		>
			<span class="font-semibold text-slate-200">{mission.subject}</span>
			<span class="text-xs text-slate-400">Prioridade: {mission.priority}</span>
		</div>
	{/each}
</div>