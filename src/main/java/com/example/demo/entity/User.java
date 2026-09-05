package com.example.demo.entity;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "api_users")
public class User {

    @Id
    private String id;
    private int apiLimit;

    public User() {} // Default constructor required by JPA

    public User(String id, int apiLimit) {
        this.id = id;
        this.apiLimit = apiLimit;
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public int getApiLimit() {
        return apiLimit;
    }

    public void setApiLimit(int apiLimit) {
        this.apiLimit = apiLimit;
    }
}