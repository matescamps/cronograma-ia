<script lang="ts">
	import { onMount } from 'svelte';

	export let speed = 0.2;
	export let starCount = 1500;

	let canvas: HTMLCanvasElement;

	onMount(() => {
		const ctx = canvas.getContext('2d');
		if (!ctx) return;

		let stars: { x: number; y: number; z: number }[] = [];

		function setup() {
			canvas.width = window.innerWidth;
			canvas.height = window.innerHeight;
			stars = [];
			for (let i = 0; i < starCount; i++) {
				stars.push({
					x: Math.random() * canvas.width,
					y: Math.random() * canvas.height,
					z: Math.random() * canvas.width
				});
			}
		}

		function draw() {
			ctx!.fillStyle = 'rgba(10, 14, 23, 1)';
			ctx!.fillRect(0, 0, canvas.width, canvas.height);

			for (let i = 0; i < stars.length; i++) {
				const star = stars[i];
				star.z -= speed;

				if (star.z <= 0) {
					star.z = canvas.width;
				}

				const k = 128 / star.z;
				const px = star.x * k + canvas.width / 2;
				const py = star.y * k + canvas.height / 2;

				if (px >= 0 && px <= canvas.width && py >= 0 && py <= canvas.height) {
					const size = (1 - star.z / canvas.width) * 2.5;
					ctx!.fillStyle = 'rgba(200, 220, 255, 0.8)';
					ctx!.beginPath();
					ctx!.arc(px, py, size, 0, Math.PI * 2);
					ctx!.fill();
				}
			}

			requestAnimationFrame(draw);
		}

		setup();
		window.addEventListener('resize', setup);
		draw();

		return () => window.removeEventListener('resize', setup);
	});
</script>

<canvas bind:this={canvas} class="fixed top-0 left-0 -z-10 w-full h-full" />