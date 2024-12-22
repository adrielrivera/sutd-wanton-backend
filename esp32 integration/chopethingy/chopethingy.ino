/**************************************************************
   Example code for ESP32 + MFRC522 + I2C LCD + PIR + Buzzer
   that calls your Flask endpoints, relying on the SERVER’s timer.
   - NO local 15s countdown. Instead we poll /get_timer_status/can_id.
   - SDA=10, RST=4 (software-like SPI, no re-wiring).
   - Strips / escapes weird characters from card_data
     so JSON parse errors won't happen on the Flask server.
**************************************************************/

#include <Arduino.h>
#include <LiquidCrystal_I2C.h>
#include "EasyMFRC522.h"

#include <WiFi.h>
#include <HTTPClient.h>

// ----------------------
//  CONFIG & DEFINES
// ----------------------
#define MAX_STRING_SIZE 100  // size of the char array read from RFID
#define BLOCK 1              // RFID memory block to read/write

// States
#define AVAILABLE    0
#define CHOPED       1
#define OCCUPIED     2
#define USER_CLASH   3
#define REMOVE_CARD  4
#define UPDATE_TIMER 5

// Card detection results
#define NO_CARD      -1
#define BAD_DATA      0
#define CARD_DETECTED 1

// LEDs, Buzzer, and PIR
#define led_red     38
#define led_yellow  37
#define led_green   36
#define buzzer_pin  35
#define pir_pin     39

// RFID pins (no hardware SPI)
#define reader_SDA  10
#define reader_RST   4

// Time intervals for PIR and user clash
unsigned long PIR_TRIGGER_LENGTH   = 5000;   // ms
unsigned long CLASH_TRIGGER_LENGTH = 2000;   // ms
unsigned int  CARD_FILTER_DELAY    = 10;     

// ----------------------------------------------------
// I2C LCD at address 0x27, 16 columns, 2 rows
// ----------------------------------------------------
LiquidCrystal_I2C lcd(0x27, 16, 2);
EasyMFRC522 rfidReader(reader_SDA, reader_RST);

// ----------------------------------------------------
// Wi-Fi & Flask server settings
// ----------------------------------------------------
const char* WIFI_SSID     = "iPhone";    // Adjust
const char* WIFI_PASSWORD = "fortnite";  // Adjust

// IP or domain for your Flask server
String serverURL          = "http://172.20.10.11:5000";

// Table ID
String tableID           = "K9";  // Must match what your server expects

// Flask endpoints
String startTimerURL     = serverURL + "/start_timer";
String endTimerURL       = serverURL + "/end_timer/";    
String setTableVacantURL = serverURL + "/set_table_vacant";
String getTimerStatusBaseURL = serverURL + "/get_timer_status/";

// Forward declarations
int  detectCard();
void printLCD(int req);
void changeState(int new_state);
int  getTimerStatusFromServer(const String &canID);
void updateTimerLCD(int remaining);

bool startTimerOnServer(String canID, String tableID);
bool endTimerOnServer(String canID);
bool setTableVacantOnServer(String tableID);

String card_data         = "";
int    prgm_state        = AVAILABLE;
unsigned long last_pir_trig   = 0;
unsigned long user_clash_trig = 0;
String choping_card           = "";

// For polling the server status
unsigned long lastStatusPoll  = 0;       // track when we last polled
unsigned long pollInterval    = 1000;    // poll every 1 second

// ----------------------------------------------------
//  Sanitize for JSON: remove/escape control chars
// ----------------------------------------------------
String sanitizeForJson(const String &input) {
  String out;
  for (int i = 0; i < input.length(); i++) {
    char c = input[i];
    // Keep printable ASCII range 32..126
    if (c >= 32 && c <= 126) {
      // Escape backslash & quote
      if (c == '\\')      out += "\\\\";
      else if (c == '\"') out += "\\\"";
      else                out += c;
    }
    // else skip or replace with something 
    // else out += '_';
  }
  return out;
}

// ----------------------------------------------------
// Basic JSON parse for remaining_time
// If parsing fails, returns -1
// ----------------------------------------------------
int parseRemainingTime(const String &jsonResponse) {
  // Example: {"table_id": "K9", "remaining_time": 891, "alerts_sent": []}
  // We'll do a naive search for "remaining_time"
  int idx = jsonResponse.indexOf("\"remaining_time\"");
  if (idx == -1) return -1;
  
  // skip ahead to the colon
  idx = jsonResponse.indexOf(":", idx);
  if (idx == -1) return -1;
  
  // read until comma or brace
  int start = idx + 1;
  int end = jsonResponse.indexOf(",", start);
  if (end == -1) {
    end = jsonResponse.indexOf("}", start);
    if (end == -1) return -1;
  }
  
  String val = jsonResponse.substring(start, end);
  val.trim();
  return val.toInt();  // if invalid, toInt() returns 0
}

// ----------------------------------------------------
void setup() {
  Serial.begin(9600);

  // Pins
  pinMode(led_red,    OUTPUT);
  pinMode(led_yellow, OUTPUT);
  pinMode(led_green,  OUTPUT);
  pinMode(buzzer_pin, OUTPUT);
  pinMode(pir_pin,    INPUT);

  // LCD
  lcd.init();
  lcd.backlight();

  // RFID (no hardware SPI)
  rfidReader.init();

  // Wi-Fi
  Serial.print("Connecting to ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.print("\nWiFi connected! IP address: ");
  Serial.println(WiFi.localIP());

  changeState(AVAILABLE);
}

// ----------------------------------------------------
void loop() {
  // Detect card
  int card_result = detectCard();
  if (card_result == CARD_DETECTED) {
    Serial.print("Card detected: ");
    Serial.println(card_data);

    // If table is free (AVAILABLE) or physically occupied (OCCUPIED),
    // scanning card means user wants to CHOPE
    if (prgm_state == AVAILABLE || prgm_state == OCCUPIED) {
      changeState(CHOPED);
    } 
    // If table is CHOPED, check if same card or user clash
    else if (prgm_state == CHOPED) {
      if (choping_card == card_data) {
        changeState(AVAILABLE);
      } else {
        Serial.println("NOT SAME USER - Clash!");
        printLCD(USER_CLASH);
        user_clash_trig = millis();
      }
    }
  }

  // PIR detection
  int pir_result = digitalRead(pir_pin);
  if ((prgm_state == AVAILABLE || prgm_state == OCCUPIED) && pir_result == HIGH) {
    changeState(OCCUPIED);
    last_pir_trig = millis();
  }
  if (prgm_state == OCCUPIED && (millis() > last_pir_trig + PIR_TRIGGER_LENGTH)) {
    changeState(AVAILABLE);
  }

  // If CHOPED: poll the server to see how much time is left
  if (prgm_state == CHOPED) {
    unsigned long now = millis();
    // Poll once every 1 second
    if (now - lastStatusPoll >= pollInterval) {
      lastStatusPoll = now;
      int remaining = getTimerStatusFromServer(choping_card);
      if (remaining > 0) {
        // Display the real time left from the server
        updateTimerLCD(remaining);
      } else {
        // Means server says "Timer not found or ended"
        // so let's revert to AVAILABLE
        changeState(AVAILABLE);
      }
    }
  }

  // If table is CHOPED but a different user tapped,
  // show the clash for CLASH_TRIGGER_LENGTH ms
  if (prgm_state == CHOPED && (millis() > user_clash_trig + CLASH_TRIGGER_LENGTH)) {
    // after the clash, we continue showing the normal countdown (handled above)
  }
}

// ----------------------------------------------------
// Reads the RFID tag using the EasyMFRC522 library
// ----------------------------------------------------
int detectCard() {
  int result;
  char string_buffer[MAX_STRING_SIZE];
  int string_size = 0;

  if (rfidReader.detectTag()) {
    string_size = rfidReader.readFile(BLOCK, "mylabel",
                                      (byte *)string_buffer,
                                      MAX_STRING_SIZE);
    // ensure null termination
    string_buffer[MAX_STRING_SIZE - 1] = 0;

    if (string_size >= 0) {
      // Prompt user to remove card
      printLCD(REMOVE_CARD);
      digitalWrite(buzzer_pin, HIGH);
      delay(300);
      digitalWrite(buzzer_pin, LOW);

      // Wait until card is removed
      int i = 0;
      while (i < CARD_FILTER_DELAY) {
        rfidReader.unselectMifareTag();
        if (rfidReader.detectTag()) i = 0;
        else i++;
      }
      result = CARD_DETECTED;
      lcd.clear();
    } else {
      result = BAD_DATA;
    }
  } else {
    result = NO_CARD;
  }
  rfidReader.unselectMifareTag();

  // Store the raw data
  card_data = String(string_buffer);
  return result;
}

// ----------------------------------------------------
// Moves table state machine to new_state
// and calls server endpoints if needed
// ----------------------------------------------------
void changeState(int new_state) {
  if (new_state == CHOPED) {
    // Turn on yellow LED
    digitalWrite(led_green,  LOW);
    digitalWrite(led_yellow, HIGH);
    digitalWrite(led_red,    LOW);
    printLCD(CHOPED);
    Serial.println("CHOPED");

    prgm_state   = CHOPED;
    choping_card = card_data;

    // Start timer on server
    startTimerOnServer(choping_card, tableID);
    return;
  }

  if (new_state == AVAILABLE) {
    // Turn on green LED
    digitalWrite(led_green,  HIGH);
    digitalWrite(led_yellow, LOW);
    digitalWrite(led_red,    LOW);
    printLCD(AVAILABLE);
    Serial.println("AVAILABLE");

    // If returning from CHOPED, user ended reservation
    if (prgm_state == CHOPED) {
      endTimerOnServer(choping_card);
      setTableVacantOnServer(tableID);
      choping_card = "";
    }
    prgm_state = AVAILABLE;
    return;
  }

  if (new_state == OCCUPIED) {
    // Turn on red LED
    digitalWrite(led_green,  LOW);
    digitalWrite(led_yellow, LOW);
    digitalWrite(led_red,    HIGH);
    printLCD(OCCUPIED);
    Serial.println("OCCUPIED");
    prgm_state = OCCUPIED;
    return;
  }
}

// ----------------------------------------------------
// Updates the LCD based on req
// ----------------------------------------------------
void printLCD(int req) {
  lcd.clear();
  lcd.setCursor(0, 0);

  if (req == CHOPED) {
    lcd.print("CHOPE-D");
    lcd.setCursor(0, 1);
    lcd.print("Waiting for Server");
    return;
  }

  if (req == REMOVE_CARD) {
    lcd.print("Pls Remove Card.");
    return;
  }

  if (req == AVAILABLE) {
    lcd.print("AVAILABLE");
    return;
  }

  if (req == OCCUPIED) {
    lcd.print("OCCUPIED");
    return;
  }

  if (req == USER_CLASH) {
    lcd.print("Someone else");
    lcd.setCursor(0, 1);
    lcd.print("chope-d already!");
    return;
  }
}

// ----------------------------------------------------
// Called when we have a valid remaining_time from server
// ----------------------------------------------------
void updateTimerLCD(int remaining) {
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("CHOPE-D");
  lcd.setCursor(0, 1);
  lcd.print("Secs Left: ");
  lcd.print(remaining);
}

// ----------------------------------------------------
// Polls the Flask server for the current timer status
// returns the remaining_time if found, else -1
// ----------------------------------------------------
int getTimerStatusFromServer(const String &canID) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Wi-Fi not connected for getTimerStatus");
    return -1;
  }

  // Build the URL for GET /get_timer_status/<can_id>
  String safeCanID = sanitizeForJson(canID);
  String url = getTimerStatusBaseURL + safeCanID;

  HTTPClient http;
  http.begin(url);
  int httpResponseCode = http.GET();

  if (httpResponseCode == 200) {
    String response = http.getString();
    Serial.print("getTimerStatus response: ");
    Serial.println(response);

    int remaining = parseRemainingTime(response);
    return remaining;
  } else {
    Serial.print("getTimerStatus error code: ");
    Serial.println(httpResponseCode);
  }
  http.end();
  return -1;
}

// ----------------------------------------------------
//  Basic server calls
// ----------------------------------------------------
bool startTimerOnServer(String canID, String tableID) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(startTimerURL); 
    http.addHeader("Content-Type", "application/json");

    String safeCanID    = sanitizeForJson(canID);
    String safeTableID  = sanitizeForJson(tableID);
    String jsonPayload = "{\"can_id\":\"" + safeCanID +
                         "\", \"table_id\":\"" + safeTableID + "\"}";

    int httpResponseCode = http.POST(jsonPayload);
    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.print("startTimer response: ");
      Serial.println(response);
    } else {
      Serial.print("startTimer error code: ");
      Serial.println(httpResponseCode);
    }
    http.end();
    return (httpResponseCode == 200);
  }
  Serial.println("Wi-Fi not connected for startTimerOnServer");
  return false;
}

bool endTimerOnServer(String canID) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String safeCanID = sanitizeForJson(canID);
    String url = endTimerURL + safeCanID;
    http.begin(url);
    http.addHeader("Content-Type", "application/json");

    int httpResponseCode = http.POST("{}");  // empty JSON
    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.print("endTimer response: ");
      Serial.println(response);
    } else {
      Serial.print("endTimer error code: ");
      Serial.println(httpResponseCode);
    }
    http.end();
    return (httpResponseCode == 200);
  }
  Serial.println("Wi-Fi not connected for endTimerOnServer");
  return false;
}

bool setTableVacantOnServer(String tableID) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(setTableVacantURL);
    http.addHeader("Content-Type", "application/json");

    String safeTableID = sanitizeForJson(tableID);
    String jsonPayload = "{\"table_id\":\"" + safeTableID + "\"}";

    int httpResponseCode = http.POST(jsonPayload);
    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.print("setTableVacant response: ");
      Serial.println(response);
    } else {
      Serial.print("setTableVacant error code: ");
      Serial.println(httpResponseCode);
    }
    http.end();
    return (httpResponseCode == 200);
  }
  Serial.println("Wi-Fi not connected for setTableVacantOnServer");
  return false;
}
