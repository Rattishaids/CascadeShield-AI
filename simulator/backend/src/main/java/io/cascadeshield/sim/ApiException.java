package io.cascadeshield.sim;

public class ApiException extends RuntimeException {
    public final int status;
    public ApiException(int status,String message){super(message);this.status=status;}
    public static ApiException invalid(String message){return new ApiException(400,message);}
    public static ApiException conflict(String message){return new ApiException(409,message);}
}
