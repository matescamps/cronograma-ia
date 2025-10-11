<script lang="ts">
	import { session } from '$lib/stores/session';
	import { fade } from 'svelte/transition';
</script>

<div
	class="w-full h-full flex flex-col p-4 sm:p-8 gap-8"
	transition:fade={{ duration: 800, delay: 200 }}
>
	<!-- HEADER: Operator Status -->
	<header class="flex justify-between items-center border-b border-slate-800 pb-4">
		<h1 class="text-xl sm:text-2xl font-bold text-slate-200 tracking-wider uppercase">
			Operator: <span class="text-blue-400">{$session.operator?.name}</span>
		</h1>
		<!-- Placeholder for Ally Status Panel -->
		<div class="text-right">
			<p class="text-slate-400">ALLY STATUS: <span class="text-green-400">ONLINE</span></p>
			<p class="text-sm text-slate-500">Recent: Organic Chemistry</p>
		</div>
	</header>

	<!-- MAIN VIEW: Past, Present, Future -->
	<main class="grid grid-cols-1 lg:grid-cols-4 gap-6 flex-1">
		<!-- PAST: War Map -->
		<section
			class="lg:col-span-1 flex flex-col gap-4 p-4 border border-slate-800 rounded-lg bg-slate-900/50"
		>
			<h2 class="text-lg font-semibold text-slate-400 uppercase tracking-widest text-center">
				Past
			</h2>
			<div class="flex-1 flex items-center justify-center text-slate-600 italic">
				[War Map of Conquered Territory]
			</div>
		</section>

		<!-- PRESENT: Current Mission -->
		<section
			class="lg:col-span-2 flex flex-col gap-4 p-6 border-2 border-blue-500/80 rounded-xl bg-slate-900/70 shadow-2xl shadow-blue-500/10"
		>
			<h2 class="text-lg font-semibold text-slate-300 uppercase tracking-widest text-center">Now</h2>
			<div class="flex-1 flex items-center justify-center text-slate-500 italic">
				[Immersive Mission Card]
			</div>
		</section>

		<!-- FUTURE: Forecast -->
		<section class="lg:col-span-1 flex flex-col gap-4 p-4 border border-slate-800 rounded-lg bg-slate-900/50">
			<h2 class="text-lg font-semibold text-slate-400 uppercase tracking-widest text-center">Future</h2>
			<div class="flex-1 flex items-center justify-center text-slate-600 italic">[AI Forecast]</div>
		</section>
	</main>
</div>