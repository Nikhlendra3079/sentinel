-- Atomic Redis fixed-window counter, aligned to Redis server time.
-- KEYS[1] = versioned policy hash
-- ARGV = limit, window_ms, cost
local limit = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local time = redis.call('TIME')
local now_ms = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
local last_ms = tonumber(redis.call('HGET', KEYS[1], 'last_ms'))
if last_ms ~= nil and now_ms < last_ms then now_ms = last_ms end
local window_id = math.floor(now_ms / window_ms)
local window_end_ms = (window_id + 1) * window_ms
local current_id = tonumber(redis.call('HGET', KEYS[1], 'window_id'))
local count = tonumber(redis.call('HGET', KEYS[1], 'count')) or 0
if current_id == nil or current_id ~= window_id then
    current_id = window_id
    count = 0
end

local allowed = 0
local retry_ms = 0
if cost > limit then
    retry_ms = -1
elseif count + cost <= limit then
    count = count + cost
    allowed = 1
else
    retry_ms = math.max(0, window_end_ms - now_ms)
end
redis.call('HSET', KEYS[1], 'window_id', current_id, 'count', count, 'last_ms', now_ms)
redis.call('PEXPIRE', KEYS[1], math.max(1000, window_end_ms - now_ms + 1000))
local remaining = math.max(0, limit - count)
local reset_ms = math.max(0, window_end_ms - now_ms)
return {allowed, string.format("%.17g", remaining), retry_ms, reset_ms, string.format("%.17g", limit)}
