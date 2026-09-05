package com.example.demo.config;

import io.github.bucket4j.grid.jcache.JCacheProxyManager;
import org.redisson.Redisson;
import org.redisson.api.RedissonClient;
import org.redisson.config.Config;
import org.redisson.jcache.configuration.RedissonConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.cache.CacheManager;
import javax.cache.Caching;
import javax.cache.Cache;
import io.github.bucket4j.distributed.proxy.ProxyManager;
import javax.cache.configuration.MutableConfiguration;

@Configuration
public class RedisConfig {

    @Bean
    public Config config() {
        Config config = new Config();
        config.useSingleServer().setAddress("redis://127.0.0.1:6379");
        return config;
    }

    @Bean(destroyMethod = "shutdown")
    public RedissonClient redissonClient(Config config) {
        return Redisson.create(config);
    }

    @Bean(name="SpringCM")
    public CacheManager cacheManager(Config config, RedissonClient redissonClient) {
        CacheManager manager = Caching.getCachingProvider().getCacheManager();
    
        // Create a standard JCache configuration
        MutableConfiguration<String, byte[]> jcacheConfig = new MutableConfiguration<>();
    
        // Bind the Redisson client to the JCache configuration
        manager.createCache("cache", RedissonConfiguration.fromInstance(redissonClient, jcacheConfig));
    
        return manager;
}

    @Bean
    public ProxyManager<String> proxyManager(CacheManager cacheManager) {
        Cache<String, byte[]> cache = cacheManager.getCache("cache");
        return new JCacheProxyManager<>(cache);
    }
}