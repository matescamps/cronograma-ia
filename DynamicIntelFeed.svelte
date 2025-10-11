<script lang="ts">
	type Intel = {
		id: number;
		type: 'Alert' | 'Intel' | 'Comms';
		message: string;
	};

	// Mock data for the intelligence feed
	const intelFeed: Intel[] = [
		{
			id: 1,
			type: 'Alert',
			message: "Your completion average in 'Organic Chemistry' is 20% below other subjects. Recommend extra review session."
		},
		{
			id: 2,
			type: 'Intel',
			message: 'New intel on the ENEM exam: the board has given more weight to text interpretation in history. Adjusting priority.'
		},
		{
			id: 3,
			type: 'Comms',
			message: 'Ally "Ana" has just completed a mission in "Physics - Kinematics".'
		},
		{
			id: 4,
			type: 'Alert',
			message: 'High difficulty reported on last 3 Math missions. Consider a "MIND MELD" session.'
		}
	];

	const getTypeClass = (type: Intel['type']) => {
		switch (type) {
			case 'Alert':
				return 'text-red-400';
			case 'Intel':
				return 'text-blue-400';
			case 'Comms':
				return 'text-green-400';
		}
	};
</script>

<div class="relative flex overflow-x-hidden border-y border-slate-800 bg-slate-900/30">
	<div class="animate-marquee whitespace-nowrap py-2">
		{#each intelFeed as item (item.id)}
			<span class="mx-8 text-sm text-slate-300">
				<strong class={getTypeClass(item.type)}>[{item.type}]</strong>
				{item.message}
			</span>
		{/each}
	</div>

	<div class="absolute top-0 animate-marquee2 whitespace-nowrap py-2">
		{#each intelFeed as item (item.id)}
			<span class="mx-8 text-sm text-slate-300">
				<strong class={getTypeClass(item.type)}>[{item.type}]</strong>
				{item.message}
			</span>
		{/each}
	</div>
</div>