package com.example.demo.filter;

import io.github.bucket4j.Bucket;
import com.example.demo.service.RateLimiter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

@Component
public class RequestFilter extends OncePerRequestFilter {

    @Autowired
    private RateLimiter rateLimiter;

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain filterChain) 
            throws ServletException, IOException {
    
        if (request.getRequestURI().startsWith("/v1")) {
            
            String userId = request.getHeader("X-Tenant");

            if (userId != null && !userId.isBlank()) {
                Bucket bucket = rateLimiter.resolveBucket(userId);

                long availableTokens = bucket.getAvailableTokens();
                System.out.println("User: " + userId + " | Available Tokens: " + availableTokens);

                if (bucket.tryConsume(1)) {
                    filterChain.doFilter(request, response);
                } else {
                    sendErrorResponse(response, HttpStatus.TOO_MANY_REQUESTS.value());
                }
            } else {
                sendErrorResponse(response, HttpStatus.FORBIDDEN.value());
            }
        } else {
            filterChain.doFilter(request, response);
        }
    }

    private void sendErrorResponse(HttpServletResponse response, int statusCode) throws IOException {
        response.setStatus(statusCode);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter().write("{\"error\": \"Rate limit exceeded or missing tenant header\", \"status\": " + statusCode + "}");
    }
}