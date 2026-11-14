-- Atomic weighted sliding-window log.
-- KEYS[1] = sorted set of event IDs scored by timestamp (ms)
-- KEYS[2] = hash mapping event ID -> request cost
-- KEYS[3] = current total usage
-- KEYS[4] = last observed Redis server timestamp (clock rollback guard)
-- ARGV = limit, window_ms, cost, unique_event_id, ttl_ms
local limit = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local event_id = ARGV[4]
local ttl_ms = tonumber(ARGV[5])
local time = redis.call('TIME')
local now_ms = tonumber(time[1]) * 1000 + math.floor(tonumber(time[2]) / 1000)
local last_ms = tonumber(redis.call('GET', KEYS[4]))
if last_ms ~= nil and now_ms < last_ms then now_ms = last_ms end
local cutoff_ms = now_ms - window_ms

local expired = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', cutoff_ms)
local used = tonumber(redis.call('GET', KEYS[3])) or 0
for _, id in ipairs(expired) do
    local expired_cost = tonumber(redis.call('HGET', KEYS[2], id)) or 0
    used = used - expired_cost
    redis.call('HDEL', KEYS[2], id)
end
if #expired > 0 then
    redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', cutoff_ms)
end
used = math.max(0, used)

local allowed = 0
local retry_ms = 0
if cost > limit then
    retry_ms = -1
elseif used + cost <= limit then
    redis.call('ZADD', KEYS[1], now_ms, event_id)
    redis.call('HSET', KEYS[2], event_id, cost)
    used = used + cost
    allowed = 1
else
    local events = redis.call('ZRANGE', KEYS[1], 0, -1, 'WITHSCORES')
    local usage_after_expiry = used
    local last_expiry = 0
    for i = 1, #events, 2 do
        local id = events[i]
        local score = tonumber(events[i + 1])
        local event_cost = tonumber(redis.call('HGET', KEYS[2], id)) or 0
        usage_after_expiry = math.max(0, usage_after_expiry - event_cost)
        last_expiry = score + window_ms
        if usage_after_expiry + cost <= limit then
            retry_ms = math.max(0, score + window_ms - now_ms)
            break
        end
    end
    if retry_ms == 0 then
        retry_ms = math.max(0, last_expiry - now_ms)
    end
end

if redis.call('ZCARD', KEYS[1]) == 0 then
    redis.call('DEL', KEYS[1], KEYS[2], KEYS[3], KEYS[4])
else
    redis.call('SET', KEYS[3], used, 'PX', ttl_ms)
    redis.call('PEXPIRE', KEYS[1], ttl_ms)
    redis.call('PEXPIRE', KEYS[2], ttl_ms)
    redis.call('SET', KEYS[4], now_ms, 'PX', ttl_ms)
end

local latest = redis.call('ZREVRANGE', KEYS[1], 0, 0, 'WITHSCORES')
local reset_ms = 0
if #latest == 2 then
    reset_ms = math.max(0, tonumber(latest[2]) + window_ms - now_ms)
end
local remaining = math.max(0, limit - used)
return {allowed, string.format("%.17g", remaining), retry_ms, reset_ms, string.format("%.17g", limit)}
