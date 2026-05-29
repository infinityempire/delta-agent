package com.deltaagent;

import android.app.Activity;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.TextView;

public class MainActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        TextView view = new TextView(this);
        view.setGravity(Gravity.CENTER);
        view.setText("Delta Agent");
        view.setTextSize(28);
        setContentView(view);
    }
}
