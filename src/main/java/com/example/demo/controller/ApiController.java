package com.example.demo.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {
    
    @GetMapping("/v1/user")
    public String getUser() {
        return "Hello Secure User";
    }

    @GetMapping("/v2/user")
    public String getUserNotSecure() {
        return "Hello Not Secure User";
    }
}