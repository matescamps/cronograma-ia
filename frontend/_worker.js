export default {
  async fetch(request, env) {
    return env.ASSETS.fetch(request);
  },
  flags: ['nodejs_compat'],
};