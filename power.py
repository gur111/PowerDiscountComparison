import pandas as pd
import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objects as go
import json
from io import StringIO
import base64

# Load the data
file_path = "meter_503_LP_02-01-2025.csv"
data = pd.read_csv(
    file_path,
    skiprows=11,
    names=["Date", "Time", "Consumption"],
    encoding="utf-8"
)
data = data.dropna()
data = data[(data["Date"].str.strip() != "") & (data["Time"].str.strip() != "")]
data["DateTime"] = pd.to_datetime(data["Date"] + " " + data["Time"], format="%d/%m/%Y %H:%M", errors="coerce")
data = data.dropna(subset=["DateTime"])
data = data[data["DateTime"] >= "2024-09-15"]
data["Consumption"] = pd.to_numeric(data["Consumption"], errors="coerce")
data = data.dropna(subset=["Consumption"])
data["Hour"] = data["DateTime"].dt.hour
data["Weekday"] = data["DateTime"].dt.weekday
data["Month"] = data["DateTime"].dt.month

# Initialize Dash app
app = dash.Dash(__name__)
discount_plans = []  # Stores multiple discount plans

# Layout
app.layout = html.Div([
    html.H1("Electricity Consumption Analysis"),

    # Input for electricity price
    html.Label("Electricity Price (per kWh):"),
    dcc.Input(id="price-input", type="number", value=0.61, step=0.01),  # Changed default value to 0.61

    # Discount plan inputs
    html.Label("Add Discount Plan:"),
    html.Div([
        html.Label("Hours Range:"),
        dcc.Input(id="start-hour", type="number", placeholder="Start Hour", min=0, max=23, step=1),
        dcc.Input(id="end-hour", type="number", placeholder="End Hour", min=0, max=23, step=1),
        html.Label("Discount Percentage:"),
        dcc.Input(id="discount", type="number", placeholder="Discount (%)", min=0, max=100, step=1),
        html.Label("Plan Type:"),
        dcc.RadioItems(
            id="plan-type",
            options=[
                {"label": "Weekdays", "value": "Weekdays"},
                {"label": "Weekends", "value": "Weekends"},
                {"label": "Both", "value": "Both"}
            ],
            value="Both",  # Default value
            labelStyle={"display": "block"}
        ),
        html.Button("Add Plan", id="add-plan", n_clicks=0)
    ]),

    # Paste JSON for Discount Plans
    html.Label("Discount Plans (JSON):"),
    dcc.Textarea(
        id="json-textarea",
        placeholder="Discount plans in JSON format",
        style={"width": "100%", "height": "100px"}
    ),

    # Upload CSV to replace data
    html.Label("Upload New Data CSV:"),
    dcc.Upload(
        id="upload-data",
        children=html.Button("Upload CSV"),
        multiple=False
    ),

    # Import Discount Plans button
    html.Button("Import Discount Plans", id="import-plans", n_clicks=0),

    # Merged Cost Summary and Discount Plans
    html.H3("Cost Summary and Discount Plans"),
    html.Div(id="cost-summary"),

    # Graphs
    dcc.Graph(id="weekday-graph"),
    dcc.Graph(id="weekend-graph"),

    # Slider for selecting the month (Moved below)
    html.Label("Select Month:"),
    dcc.Slider(
        id="month-slider",
        min=data["Month"].min(),
        max=data["Month"].max(),
        step=1,
        marks={i: f"Month {i}" for i in range(data["Month"].min(), data["Month"].max() + 1)},
        value=data["Month"].min()
    )
])


@app.callback(
    [Output("weekday-graph", "figure"),
     Output("weekend-graph", "figure"),
     Output("cost-summary", "children"),
     Output("json-textarea", "value")],
    [Input("month-slider", "value"),
     Input("price-input", "value"),
     Input("add-plan", "n_clicks"),
     Input("upload-data", "contents"),
     Input("import-plans", "n_clicks")],
    [State("start-hour", "value"),
     State("end-hour", "value"),
     State("discount", "value"),
     State("plan-type", "value"),
     State("upload-data", "filename"),
     State("json-textarea", "value")]
)
def update_dashboard(selected_month, price, n_clicks, contents, import_n_clicks, start_hour, end_hour, discount, plan_type, filename, json_value):
    global data

    # Import plans from JSON if the import button is clicked
    if import_n_clicks > 0 and json_value:
        try:
            imported_plans = json.loads(json_value)
            global discount_plans
            discount_plans = imported_plans  # Replace existing plans with the imported ones
        except json.JSONDecodeError:
            return dash.no_update  # Do nothing if the JSON is invalid

    # Handle file upload and CSV import
    if contents:
        content_type, content_string = contents.split(',')
        decoded = StringIO(base64.b64decode(content_string).decode("utf-8"))
        new_data = pd.read_csv(decoded, skiprows=11, names=["Date", "Time", "Consumption"], encoding="utf-8")

        data = new_data.dropna()
        data = data[(data["Date"].str.strip() != "") & (data["Time"].str.strip() != "")]
        data["DateTime"] = pd.to_datetime(data["Date"] + " " + data["Time"], format="%d/%m/%Y %H:%M", errors="coerce")
        data = data.dropna(subset=["DateTime"])
        data["Consumption"] = pd.to_numeric(data["Consumption"], errors="coerce")
        data = data.dropna(subset=["Consumption"])
        data["Hour"] = data["DateTime"].dt.hour
        data["Weekday"] = data["DateTime"].dt.weekday
        data["Month"] = data["DateTime"].dt.month

    # Adding new discount plan if the button is clicked
    if n_clicks > 0 and start_hour is not None and end_hour is not None and discount is not None and plan_type:
        discount_plans.append({
            "start_hour": start_hour,
            "end_hour": end_hour,
            "discount": discount,
            "plan_type": plan_type
        })

    filtered_data = data[data["Month"] == selected_month]
    workdays = filtered_data[filtered_data["Weekday"].isin([0, 1, 2, 3, 4])]
    weekends = filtered_data[filtered_data["Weekday"].isin([5, 6])]

    cost_summary = []

    for i, plan in enumerate(discount_plans):
        temp_workdays = workdays.copy()
        temp_weekends = weekends.copy()
        total_discount = 0

        # Handling overnight discount
        if plan["plan_type"] in ["Weekdays", "Both"]:
            if plan["start_hour"] > plan["end_hour"]:  # Overnight discount (e.g., 23:00 to 06:00)
                mask1 = (temp_workdays["Hour"] >= plan["start_hour"])  # From start_hour to 23:59
                mask2 = (temp_workdays["Hour"] <= plan["end_hour"])  # From 00:00 to end_hour
                total_discount += temp_workdays.loc[mask1, "Consumption"].sum() * (plan["discount"] / 100)
                temp_workdays.loc[mask1, "Consumption"] *= (1 - plan["discount"] / 100)
                total_discount += temp_workdays.loc[mask2, "Consumption"].sum() * (plan["discount"] / 100)
                temp_workdays.loc[mask2, "Consumption"] *= (1 - plan["discount"] / 100)
            else:
                mask = (temp_workdays["Hour"] >= plan["start_hour"]) & (temp_workdays["Hour"] <= plan["end_hour"])
                total_discount += temp_workdays.loc[mask, "Consumption"].sum() * (plan["discount"] / 100)
                temp_workdays.loc[mask, "Consumption"] *= (1 - plan["discount"] / 100)

        if plan["plan_type"] in ["Weekends", "Both"]:
            if plan["start_hour"] > plan["end_hour"]:  # Overnight discount (e.g., 23:00 to 06:00)
                mask1 = (temp_weekends["Hour"] >= plan["start_hour"])  # From start_hour to 23:59
                mask2 = (temp_weekends["Hour"] <= plan["end_hour"])  # From 00:00 to end_hour
                total_discount += temp_weekends.loc[mask1, "Consumption"].sum() * (plan["discount"] / 100)
                temp_weekends.loc[mask1, "Consumption"] *= (1 - plan["discount"] / 100)
                total_discount += temp_weekends.loc[mask2, "Consumption"].sum() * (plan["discount"] / 100)
                temp_weekends.loc[mask2, "Consumption"] *= (1 - plan["discount"] / 100)
            else:
                mask = (temp_weekends["Hour"] >= plan["start_hour"]) & (temp_weekends["Hour"] <= plan["end_hour"])
                total_discount += temp_weekends.loc[mask, "Consumption"].sum() * (plan["discount"] / 100)
                temp_weekends.loc[mask, "Consumption"] *= (1 - plan["discount"] / 100)

        total_cost = (temp_workdays["Consumption"].sum() + temp_weekends["Consumption"].sum()) * price
        cost_summary.append(f"Plan {i + 1}: Total Cost = {total_cost:.2f}, Total Discount = {total_discount:.2f}")

    workdays_avg = workdays.groupby("Hour")["Consumption"].mean()
    weekends_avg = weekends.groupby("Hour")["Consumption"].mean()
    weekday_fig = go.Figure(go.Bar(x=workdays_avg.index, y=workdays_avg, name="Workdays"))
    weekend_fig = go.Figure(go.Bar(x=weekends_avg.index, y=weekends_avg, name="Weekends"))
    weekday_fig.update_layout(title="Average Consumption - Workdays", xaxis_title="Hour", yaxis_title="Average Consumption (kWh)")
    weekend_fig.update_layout(title="Average Consumption - Weekends", xaxis_title="Hour", yaxis_title="Average Consumption (kWh)")

    # Update JSON Textarea
    json_output = json.dumps(discount_plans, indent=4)

    # Combine Cost Summary and Discount Plans
    cost_summary_html = html.Ul([html.Li(summary) for summary in cost_summary])
    discount_plans_html = html.Ul([html.Li(f"Plan {i + 1}: {plan['start_hour']}-{plan['end_hour']} hrs, {plan['discount']}% off ({plan['plan_type']})")
                                   for i, plan in enumerate(discount_plans)])

    return weekday_fig, weekend_fig, html.Div([cost_summary_html, html.H4("Discount Plans:"), discount_plans_html]), json_output


# Run the app
#if __name__ == "__main__":
#    app.run_server(debug=True)

if __name__ == "__main__":
    app.run_server(debug=False, host='0.0.0.0', port=80)
