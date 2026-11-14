-- Atomic Redis token bucket.
-- KEYS[1] = versioned bucket hash
-- ARGV = capacity, refill_per_ms, cost, ttl_ms
local capacity = tonumber(ARGV[1])
local refill_per_ms = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local ttl_ms = tonumber(ARGV[4])

local time = redis.call('TIME')
local now_ms = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
local tokens = tonumber(redis.call('HGET', KEYS[1], 'tokens'))
local last_ms = tonumber(redis.call('HGET', KEYS[1], 'updated_at_ms'))
if tokens == nil then tokens = capacity end
if last_ms == nil then last_ms = now_ms end
if now_ms < last_ms then now_ms = last_ms end

tokens = math.min(capacity, tokens + ((now_ms - last_ms) * refill_per_ms))
local allowed = 0
local retry_ms = 0
if cost > capacity then
    retry_ms = -1
elseif tokens >= cost then
    tokens = tokens - cost
    allowed = 1
else
    retry_ms = math.ceil((cost - tokens) / refill_per_ms)
end

redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated_at_ms', now_ms)
redis.call('PEXPIRE', KEYS[1], ttl_ms)
local remaining = math.max(0, tokens)
local reset_ms = math.ceil((capacity - remaining) / refill_per_ms)
return {allowed, string.format("%.17g", remaining), retry_ms, reset_ms, string.format("%.17g", capacity)}
