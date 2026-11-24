package org.safeflight.android.ui.widget;

import android.content.Context;
import android.content.res.TypedArray;
import android.util.AttributeSet;
import android.view.LayoutInflater;
import android.widget.LinearLayout;

import androidx.annotation.ColorRes;
import androidx.core.content.ContextCompat;

import org.safeflight.android.R;
import org.safeflight.android.databinding.ViewTelemetryRowBinding;
import org.safeflight.android.ui.UiFormat;

/**
 * One "label ........ value" row. The label is set in XML with
 * {@code app:rowLabel="Altitud rel."}; the value from Java with {@link #setValue}.
 * Layout: res/layout/view_telemetry_row.xml.
 */
public final class TelemetryRowView extends LinearLayout {
    private final ViewTelemetryRowBinding binding;
    private String shownValue;
    private int shownColor;

    public TelemetryRowView(Context context) {
        this(context, null);
    }

    public TelemetryRowView(Context context, AttributeSet attrs) {
        super(context, attrs);
        setOrientation(HORIZONTAL);
        binding = ViewTelemetryRowBinding.inflate(LayoutInflater.from(context), this);
        if (attrs != null) {
            TypedArray a = context.obtainStyledAttributes(attrs, R.styleable.TelemetryRowView);
            binding.rowLabel.setText(a.getString(R.styleable.TelemetryRowView_rowLabel));
            a.recycle();
        }
        setValue(UiFormat.UNKNOWN, R.color.sf_text);
    }

    public void setLabel(String label) {
        binding.rowLabel.setText(label);
    }

    /** Unknown values ("—") are always shown in grey. */
    public void setValue(String value, @ColorRes int color) {
        int c = UiFormat.UNKNOWN.equals(value) ? R.color.sf_muted : color;
        if (value.equals(shownValue) && c == shownColor) {
            return; // unchanged: no redraw
        }
        shownValue = value;
        shownColor = c;
        binding.rowValue.setText(value);
        binding.rowValue.setTextColor(ContextCompat.getColor(getContext(), c));
    }

    public void setValue(String value) {
        setValue(value, R.color.sf_text);
    }
}
