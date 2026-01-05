# Frontend Rate Limit Handling Guide

## Issue: Rate Limit Exceeded

Your frontend is correctly calling the API, but hitting the rate limit. Here's how to handle it:

---

## Immediate Solutions

### 1. **Restart Your Backend Server** (Quickest Fix)

If rate limits are stored in memory (not Redis), restarting the server clears them:

```bash
# Stop the server (Ctrl+C)
# Then restart:
python -m app.main
```

### 2. **Increase Rate Limit for Development**

Add to your `.env` file:

```bash
MAX_REQUESTS_PER_WINDOW=100
RATE_LIMIT_WINDOW_HOURS=1
```

Then restart the server.

### 3. **Wait for Rate Limit to Expire**

The rate limit resets after 1 hour. Wait and try again.

---

## Frontend Error Handling

Update your frontend to handle rate limit errors gracefully:

```javascript
const handleSendOTP = async () => {
  try {
    const response = await fetch(`${API_BASE_URL}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: phoneNumber }),
    });

    const data = await response.json();

    if (data.success) {
      // OTP sent successfully
      setShowOTPInput(true);
    } else {
      // Handle error
      const errorCode = data.data?.error;
      
      if (errorCode === 'RATE_LIMIT_EXCEEDED') {
        const retryAfter = data.data?.retry_after_seconds || 3600;
        const hours = Math.ceil(retryAfter / 3600);
        
        Alert.alert(
          'Rate Limit Exceeded',
          `Too many OTP requests. Please try again in ${hours} hour(s).`,
          [
            { text: 'OK', style: 'default' },
            { 
              text: 'Wait', 
              onPress: () => {
                // Optionally start a countdown timer
                startCountdown(retryAfter);
              }
            }
          ]
        );
      } else if (errorCode === 'USER_NOT_FOUND') {
        Alert.alert('User Not Found', 'Please register first.');
        navigation.navigate('Register');
      } else {
        Alert.alert('Error', data.message || 'Failed to send OTP');
      }
    }
  } catch (error) {
    Alert.alert('Error', error.message || 'Network error');
  }
};
```

---

## Better User Experience

Show a countdown timer when rate limited:

```javascript
const [rateLimitCountdown, setRateLimitCountdown] = useState(null);

const startCountdown = (seconds) => {
  setRateLimitCountdown(seconds);
  
  const interval = setInterval(() => {
    setRateLimitCountdown((prev) => {
      if (prev <= 1) {
        clearInterval(interval);
        return null;
      }
      return prev - 1;
    });
  }, 1000);
};

// In your UI
{rateLimitCountdown && (
  <Text>
    Rate limited. Try again in {Math.floor(rateLimitCountdown / 60)}:
    {(rateLimitCountdown % 60).toString().padStart(2, '0')}
  </Text>
)}
```

---

## Development vs Production

**For Development:**
- Set `MAX_REQUESTS_PER_WINDOW=100` in `.env`
- Restart server frequently to clear memory-based limits

**For Production:**
- Keep `MAX_REQUESTS_PER_WINDOW=10` (current default)
- Handle rate limit errors gracefully in frontend
- Show user-friendly messages

---

## Current Status

✅ **Your frontend is working correctly!**
- API calls are being made
- Responses are being received
- Error handling is working

❌ **Issue:** Rate limit exceeded (10 requests/hour)

**Fix:** Restart server or increase limit for development

