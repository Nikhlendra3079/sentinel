package com.example.demo.service;

import io.github.bucket4j.Bucket;
import io.github.bucket4j.BucketConfiguration;
import io.github.bucket4j.distributed.proxy.ProxyManager;
import com.example.demo.entity.User;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.function.Supplier;

@Service
public class RateLimiter {

    @Autowired
    private UserService userService;

    @Autowired
    private ProxyManager<String> proxyManager;

    public Bucket resolveBucket(String userId) {
        Supplier<BucketConfiguration> configSupplier = getConfigSupplierForUser(userId);
        return proxyManager.builder().build(userId, configSupplier);
    }

    private Supplier<BucketConfiguration> getConfigSupplierForUser(String userId) {
        User user = userService.getUser(userId);
        int apiLimit = (user != null) ? user.getApiLimit() : 1;

        return () -> BucketConfiguration.builder()
                .addLimit(limit -> limit.capacity(apiLimit).refillIntervally(apiLimit, Duration.ofMinutes(1)))
                .build();
    }
}