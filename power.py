import pandas as pd
import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objects as go
import json
from io import StringIO
import base64
from flask import session
from flask_session import Session

# Load the data
file_path = "meter.csv"
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
data["Consumption"] = pd.to_numeric(data["Consumption"], errors="coerce")
data = data.dropna(subset=["Consumption"])
data["Hour"] = data["DateTime"].dt.hour
data["Weekday"] = data["DateTime"].dt.weekday
data["Month"] = data["DateTime"].dt.month

# Initialize Dash app
app = dash.Dash(__name__)
app.server.secret_key = 'your-secret-key'  # For session management
app.server.config['SESSION_TYPE'] = 'filesystem'
Session(app.server)

discount_plans = [
    {
        "start_hour": 0,
        "end_hour": 23,
        "discount": 7,
        "plan_type": "Both"
    },
    {
        "start_hour": 23,
        "end_hour": 16,
        "discount": 10,
        "plan_type": "Both"
    },
    {
        "start_hour": 23,
        "end_hour": 6,
        "discount": 20,
        "plan_type": "Both"
    },
    {
        "start_hour": 14,
        "end_hour": 19,
        "discount": 18,
        "plan_type": "Both"
    },
    {
        "start_hour": 6,
        "end_hour": 16,
        "discount": 15,
        "plan_type": "Weekdays"
    }
]  # Stores multiple discount plans

# Layout
app.layout = html.Div([
    html.H1("Electricity Consumption Analysis"),
    html.Div([
        html.Div("קבלת קובץ אקסל עם נתוני צריכה מהשנה האחרונה למייל שלך."),
        html.A('Link to download data from חברת חשמל',href='https://www.iec.co.il/consumption-info-menu/remote-reading-info', target='_blank')
    ]),

    # Input for electricity price
    html.H3("Electricity Price (per kWh):"),
    dcc.Input(id="price-input", type="number", value=0.61, step=0.01),  # Changed default value to 0.61
    html.Span('ILS'),
    # Discount plan inputs
    html.H3("Add Discount Plan:"),
    html.Div([
        html.Label("Hours Range:"),
        dcc.Input(id="start-hour", type="number", placeholder="Start Hour", min=0, max=23, step=1, style={"width": "100px"}),
        dcc.Input(id="end-hour", type="number", placeholder="End Hour", min=0, max=23, step=1, style={"width": "100px"}),
        html.Br(),
        html.Label("Discount Percentage:"),
        dcc.Input(id="discount", type="number", placeholder="Discount (%)", min=0, max=100, step=1, style={"width": "100px"}),
        html.Br(),
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
    html.H3("Discount Plans (JSON):"),
    dcc.Textarea(
        id="json-textarea",
        placeholder="Discount plans in JSON format",
        style={"width": "100%", "height": "100px"}
    ),
    # Import Discount Plans button
    html.Button("Import Discount Plans", id="import-plans", n_clicks=0),

    # Upload CSV to replace data
    html.H3("Upload New Data CSV:"),
    dcc.Upload(
        id="upload-data",
        children=html.Button("Upload CSV"),
        multiple=False
    ),

    # Merged Cost Summary and Discount Plans
    html.H3("Cost Summary and Discount Plans"),
    html.Div(id="cost-summary"),

    # Slider for selecting the month (Moved below)
    html.H3("Select Month:"),
    dcc.Slider(
        id="month-slider",
        min=data["Month"].min(),
        max=data["Month"].max(),
        step=1,
        marks={i: f"Month {i}" for i in range(data["Month"].min(), data["Month"].max() + 1)},
        value=data["Month"].min()
    ),

    # Graphs placed below the slider
    dcc.Graph(id="weekday-graph"),
    dcc.Graph(id="weekend-graph"),
    html.Div('This tool was created by Gur Telem but actually it is almost purely ChatGPT. Some might say it is modern programming.'),
])


def get_session_data():
    """Get the session-specific data. Initialize if not present."""
    if "data" not in session:
        session["data"] = data.to_dict()  # Store the initial data globally as default
    return pd.DataFrame(session["data"])


def set_session_data(new_data):
    """Update the session-specific data."""
    session["data"] = new_data.to_dict()


def get_session_plans():
    """Get the session-specific discount plans. Initialize if not present."""
    if "discount_plans" not in session:
        session["discount_plans"] = discount_plans
    return session["discount_plans"]


def set_session_plans(new_plans):
    """Update the session-specific discount plans."""
    session["discount_plans"] = new_plans


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
    ses_data = get_session_data()

    # if not ses_data or not ses_discount_plans:
    #     ses_data = data.copy()

    # Import plans from JSON if the import button is clicked
    if import_n_clicks > 0 and json_value:
        try:
            imported_plans = json.loads(json_value)
            set_session_plans(imported_plans)  # Replace existing plans with the imported ones
        except json.JSONDecodeError:
            return dash.no_update  # Do nothing if the JSON is invalid

    ses_discount_plans = get_session_plans()

    # Handle file upload and CSV import
    if contents:
        content_type, content_string = contents.split(',')
        decoded = StringIO(base64.b64decode(content_string).decode("utf-8"))
        new_data = pd.read_csv(decoded, skiprows=11, names=["Date", "Time", "Consumption"], encoding="utf-8")

        ses_data = new_data.dropna()
        ses_data = ses_data[(ses_data["Date"].str.strip() != "") & (ses_data["Time"].str.strip() != "")]
        ses_data["DateTime"] = pd.to_datetime(ses_data["Date"] + " " + ses_data["Time"], format="%d/%m/%Y %H:%M", errors="coerce")
        ses_data = ses_data.dropna(subset=["DateTime"])
        ses_data["Consumption"] = pd.to_numeric(ses_data["Consumption"], errors="coerce")
        ses_data = ses_data.dropna(subset=["Consumption"])
        ses_data["Hour"] = ses_data["DateTime"].dt.hour
        ses_data["Weekday"] = ses_data["DateTime"].dt.weekday
        ses_data["Month"] = ses_data["DateTime"].dt.month

    # Adding new discount plan if the button is clicked
    if n_clicks > 0 and start_hour is not None and end_hour is not None and discount is not None and plan_type:
        ses_discount_plans.append({
            "start_hour": start_hour,
            "end_hour": end_hour,
            "discount": discount,
            "plan_type": plan_type
        })

    filtered_data = ses_data[ses_data["Month"] == selected_month]
    workdays = filtered_data[filtered_data["Weekday"].isin([0, 1, 2, 3, 4])]
    weekends = filtered_data[filtered_data["Weekday"].isin([5, 6])]

    cost_summary = []

    for i, plan in enumerate(ses_discount_plans):
        temp_workdays = workdays.copy()
        temp_weekends = weekends.copy()
        total_discount = 0

        # Handling overnight discount
        if plan["plan_type"] in ["Weekdays", "Both"]:
            if plan["start_hour"] > plan["end_hour"]:  # Overnight discount (e.g., 23:00 to 06:00)
                mask1 = (temp_workdays["Hour"] >= plan["start_hour"])  # From start_hour to 23:59
                mask2 = (temp_workdays["Hour"] <= plan["end_hour"])  # From 00:00 to end_hour
                total_discount += temp_workdays.loc[mask1 | mask2, "Consumption"].sum() * (plan["discount"] / 100)

            else:  # Standard discount (e.g., 6:00 to 16:00)
                mask = (temp_workdays["Hour"] >= plan["start_hour"]) & (temp_workdays["Hour"] < plan["end_hour"])
                total_discount += temp_workdays.loc[mask, "Consumption"].sum() * (plan["discount"] / 100)

        # Applying discount for weekends
        if plan["plan_type"] in ["Weekends", "Both"]:
            if plan["start_hour"] > plan["end_hour"]:  # Overnight discount
                mask1 = (temp_weekends["Hour"] >= plan["start_hour"])  # From start_hour to 23:59
                mask2 = (temp_weekends["Hour"] <= plan["end_hour"])  # From 00:00 to end_hour
                total_discount += temp_weekends.loc[mask1 | mask2, "Consumption"].sum() * (plan["discount"] / 100)
            else:  # Standard discount
                mask = (temp_weekends["Hour"] >= plan["start_hour"]) & (temp_weekends["Hour"] < plan["end_hour"])
                total_discount += temp_weekends.loc[mask, "Consumption"].sum() * (plan["discount"] / 100)

        total_discount_ils = total_discount * price
        cost_summary.append(
            f"Plan {i + 1}: {plan['discount']}% discount from {plan['start_hour']}:00 to {plan['end_hour']}:59 for {plan['plan_type']} - Total Discount: {total_discount_ils:.2f} ILS\n")

    # Create graphs for weekday and weekend
    weekday_consumption = workdays.groupby("Hour")["Consumption"].mean()
    weekend_consumption = weekends.groupby("Hour")["Consumption"].mean()

    weekday_figure = go.Figure()
    weekday_figure.add_trace(go.Bar(
        x=weekday_consumption.index,
        y=weekday_consumption.values,
        name="Weekdays Consumption",
        marker=dict(color='blue')
    ))
    weekday_figure.update_layout(
        title="Average Hourly Consumption - Weekdays",
        xaxis_title="Hour",
        yaxis_title="Average Consumption (kWh)",
        barmode="group"
    )

    weekend_figure = go.Figure()
    weekend_figure.add_trace(go.Bar(
        x=weekend_consumption.index,
        y=weekend_consumption.values,
        name="Weekend Consumption",
        marker=dict(color='orange')
    ))
    weekend_figure.update_layout(
        title="Average Hourly Consumption - Weekends",
        xaxis_title="Hour",
        yaxis_title="Average Consumption (kWh)",
        barmode="group"
    )
    cost_summary_html = html.Div([html.Div(summary) for summary in cost_summary])
    set_session_data(ses_data)
    set_session_plans(ses_discount_plans)
    return weekday_figure, weekend_figure, cost_summary_html, json.dumps(ses_discount_plans, indent=4)


server = app.server

# Run the app
if __name__ == "__main__":
    app.run_server(debug=True)
