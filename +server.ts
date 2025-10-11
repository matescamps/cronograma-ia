import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import Groq from 'groq-sdk';
import { GROQ_API_KEY } from '$env/static/private';
import { z } from 'zod';

const groq = new Groq({ apiKey: GROQ_API_KEY });

const MindMeldSchema = z.object({
	subject: z.string(),
	activity: z.string().optional(),
	comment: z.string().optional()
});

export const POST: RequestHandler = async ({ request }) => {
	const validation = MindMeldSchema.safeParse(await request.json());

	if (!validation.success) {
		return json({ error: 'Invalid mission data for MIND MELD.' }, { status: 400 });
	}

	const { subject, activity, comment } = validation.data;

	const prompt = `
        You are a Socratic mentor AI for a learning system called Focus OS.
        An operator has pressed an emergency "MIND MELD" button because they are struggling.
        Your task is to provide radical new perspectives, not generic textbook explanations.

        Mission Data:
        - Subject: ${subject}
        - Activity: ${activity || 'Not specified'}
        - Operator's Last Comment: "${comment || 'None'}"

        Your response MUST be ONLY a valid JSON object with the structure:
        {
          "perspectives": ["Three radical new perspectives to understand this concept."],
          "challenge_question": "A single, challenging question that forces a different way of thinking."
        }
    `;

	try {
		const chatCompletion = await groq.chat.completions.create({
			messages: [{ role: 'system', content: "You are an AI that only responds with valid JSON." }, { role: 'user', content: prompt }],
			model: 'llama3-8b-8192',
			temperature: 0.8,
			response_format: { type: 'json_object' }
		});

		const mindMeldResponse = JSON.parse(chatCompletion.choices[0]?.message?.content || '{}');
		return json(mindMeldResponse);
	} catch (error) {
		console.error('MIND MELD Error:', error);
		return json({ error: 'Failed to initiate MIND MELD with Oracle.' }, { status: 500 });
	}
};