# Goal

Address high priority issues

## Issues To Address

**Extensibility is HIGH Priority**

I hold Layered Architecture by modular abstraction above all other software engineering best practices and architectural design principles. I find that with proper layering and abstraction, any wrong can be righted, complexity is easier to reduce, performance is easier to optimize with dependency injection, and so on and so on.

From the highest level, I already see the need for a provider interface extracted from the CLaude Code CLI/SDK. We should be able to decide at runtime whether we spawn a Claude Code instance or an OpenCode instance, or AmazonQ instance, or GPTme instance.

For this first MVP/Walking Skeleton approach dictates at LEAST supporting two (Claude Code, OpenCode) both with a common interface extracted. For MVP, i think we should at least provide a way to create a session with a supported model (i.e. Opus4.1, etc for claude; openrouter/Kimi-k2, deepseek for opencode)

**Duplicate Code**

There should be NO duplicated or redundant code shared between /app and /src/jelmore.

- This is clearly an artifact caused by unclear architectural direction.
  - This code is more "competing" rather than duplicated
  - It feels almost as if two developers each had their own idea of how to implement and both somehow made it in.

**Competing Logging Strategies**

This is another symptom of lack of architectural direction. A logger needs to be decided and that's the logger that is used throughout the service - no acceptions

**Security**

Don't care as much because:

1. this is not production code.
2. I am and will be the only user for the immediate time being
3. I can always keep behind my vpn or add a simple traefik middleware auth layer

- That said...API key is easy enough. Let's do that

**Session Storage**

Agreed. Should be moved to redis.

**Traefik Labels**

YES! Do it!
