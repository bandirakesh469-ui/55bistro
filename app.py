import os, json, sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bistro.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "55bistro-change-this-secret")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024
ALLOWED = {"png", "jpg", "jpeg", "webp", "gif"}

CONTACT = {
    "phone": "+91 94947 29944",
    "phone_link": "tel:+919494729944",
    "whatsapp": "https://wa.me/919494729944",
    "instagram": "https://www.instagram.com/55bistro/",
    "facebook": "https://www.facebook.com/55bistro/",
    "address": "55 Bistro, 3rd Floor, Sreeman Enclave, Opp. Kings Court Apartment, Srihari Nagar, Magunta Layout, Nellore, Andhra Pradesh – 524003, India",
    "map": "https://www.google.com/maps/dir/?api=1&destination=55+Bistro%2C+Sreeman+Enclave%2C+Srihari+Nagar%2C+Magunta+Layout%2C+Nellore%2C+Andhra+Pradesh+524003",
}
CATEGORIES = ["Starters","Soups","Salads","Main Course","Biryani","Chinese","Tandoori","Breads","Desserts","Beverages","Mocktails","Cocktails","Kids","Combos","Specials"]

def db():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c

def init_db():
    c=db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS admin(id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT);
    CREATE TABLE IF NOT EXISTS food_items(
      id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL,
      price REAL NOT NULL, description TEXT, image TEXT, rating REAL DEFAULT 0,
      rating_count INTEGER DEFAULT 0, admin_rating REAL DEFAULT 0, admin_rating_count INTEGER DEFAULT 0,
      order_count INTEGER DEFAULT 0, available INTEGER DEFAULT 1, created_at TEXT);
    CREATE TABLE IF NOT EXISTS orders(
      id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT, phone TEXT, items TEXT,
      total REAL, status TEXT DEFAULT 'Pending', created_at TEXT);
    CREATE TABLE IF NOT EXISTS bookings(
      id INTEGER PRIMARY KEY AUTOINCREMENT, customer_name TEXT, phone TEXT, guests INTEGER,
      booking_date TEXT, booking_time TEXT, duration_hours REAL, notes TEXT,
      status TEXT DEFAULT 'Pending', created_at TEXT);
    CREATE TABLE IF NOT EXISTS offers(
      id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, description TEXT, poster TEXT,
      active INTEGER DEFAULT 1, created_at TEXT);
    """)
    if not c.execute("SELECT 1 FROM admin LIMIT 1").fetchone():
        c.execute("INSERT INTO admin(username,password) VALUES(?,?)",("55Bistro","1234@qwer"))
    if not c.execute("SELECT 1 FROM food_items LIMIT 1").fetchone():
        samples=[
          ("Rooftop Butter Chicken","Main Course",349,"Rich creamy tomato gravy with tandoor chicken.",4.8,126),
          ("Paneer Tikka Masala","Main Course",289,"Char-grilled paneer in smoky masala sauce.",4.6,94),
          ("Sunset Special Pizza","Starters",399,"Wood-fired pizza with peppers, olives and mozzarella.",4.7,81),
          ("Peri Peri Fries","Starters",149,"Crispy fries with tangy peri-peri seasoning.",4.4,62),
          ("Chocolate Lava Cake","Desserts",179,"Warm molten chocolate with vanilla ice cream.",4.9,143),
          ("55 Signature Mocktail","Mocktails",199,"Fresh mint, citrus and the house signature blend.",4.5,77)]
        for n,cat,p,d,r,rc in samples:
            c.execute("""INSERT INTO food_items(name,category,price,description,rating,rating_count,admin_rating,admin_rating_count,order_count,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""",(n,cat,p,d,r,rc,r,1,rc,datetime.now().isoformat()))
    c.commit(); c.close()

def admin_required(f):
    @wraps(f)
    def w(*a,**k):
        if not session.get("admin_logged_in"): return redirect(url_for("admin_login"))
        return f(*a,**k)
    return w

def valid_file(f):
    return f and "." in f.filename and f.filename.rsplit(".",1)[1].lower() in ALLOWED

@app.context_processor
def inject():
    return {"contact":CONTACT,"categories":CATEGORIES}

@app.route("/")
def index():
    c=db()
    items=c.execute("SELECT * FROM food_items WHERE available=1 ORDER BY category,id").fetchall()
    offers=c.execute("SELECT * FROM offers WHERE active=1 ORDER BY id DESC").fetchall()
    c.close()
    menu={}
    for x in items: menu.setdefault(x["category"],[]).append(x)
    return render_template("index.html",menu=menu,offers=offers)

@app.route("/api/order",methods=["POST"])
def order():
    d=request.get_json(silent=True) or {}
    name=(d.get("name") or "").strip(); phone=(d.get("phone") or "").strip(); cart=d.get("cart") or []
    if not name or not phone or not cart: return jsonify(ok=False,message="Please enter your name, phone number and at least one item."),400
    total=sum(float(i.get("price",0))*int(i.get("qty",0)) for i in cart)
    c=db()
    c.execute("INSERT INTO orders(customer_name,phone,items,total,created_at) VALUES(?,?,?,?,?)",(name,phone,json.dumps(cart),total,datetime.now().strftime("%Y-%m-%d %H:%M")))
    for i in cart:
        c.execute("UPDATE food_items SET order_count=order_count+? WHERE id=?",(int(i.get("qty",0)),int(i["id"])))
    c.commit(); c.close()
    return jsonify(ok=True,message="Order received. 55 Bistro will contact you shortly.")

@app.route("/api/rating",methods=["POST"])
def rating():
    d=request.get_json(silent=True) or {}
    try: item_id=int(d["item_id"]); stars=max(1,min(5,float(d["rating"])))
    except: return jsonify(ok=False,message="Invalid rating."),400
    c=db(); x=c.execute("SELECT rating,rating_count FROM food_items WHERE id=?",(item_id,)).fetchone()
    if not x: c.close(); return jsonify(ok=False,message="Item not found."),404
    new=(x["rating"]*x["rating_count"]+stars)/(x["rating_count"]+1)
    c.execute("UPDATE food_items SET rating=?,rating_count=rating_count+1 WHERE id=?",(round(new,1),item_id))
    c.commit(); c.close(); return jsonify(ok=True,rating=round(new,1),message="Thank you for your rating.")

@app.route("/book-table",methods=["POST"])
def book():
    d=request.get_json(silent=True) or {}
    required=["name","phone","guests","date","time","duration"]
    if not all(d.get(x) for x in required): return jsonify(ok=False,message="Please complete all booking fields."),400
    c=db()
    c.execute("""INSERT INTO bookings(customer_name,phone,guests,booking_date,booking_time,duration_hours,notes,created_at)
                 VALUES(?,?,?,?,?,?,?,?)""",(d["name"],d["phone"],int(d["guests"]),d["date"],d["time"],float(d["duration"]),d.get("notes",""),datetime.now().strftime("%Y-%m-%d %H:%M")))
    c.commit(); c.close(); return jsonify(ok=True,message="Table booking request submitted. 55 Bistro will confirm it shortly.")

@app.route("/admin/login",methods=["GET","POST"])
def admin_login():
    if request.method=="POST":
        c=db(); a=c.execute("SELECT * FROM admin WHERE username=? AND password=?",(request.form.get("username","").strip(),request.form.get("password",""))).fetchone(); c.close()
        if a: session["admin_logged_in"]=True; session["admin_username"]=a["username"]; return redirect(url_for("admin_dashboard"))
        flash("Invalid username or password.","error")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def logout(): session.clear(); return redirect(url_for("admin_login"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    c=db()
    items=c.execute("SELECT * FROM food_items ORDER BY category,id").fetchall()
    orders=c.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    bookings=c.execute("SELECT * FROM bookings ORDER BY id DESC").fetchall()
    offers=c.execute("SELECT * FROM offers ORDER BY id DESC").fetchall()
    stats={
      "orders":c.execute("SELECT COUNT(*) n FROM orders").fetchone()["n"],
      "revenue":c.execute("SELECT COALESCE(SUM(total),0) n FROM orders WHERE status!='Rejected'").fetchone()["n"],
      "pending":c.execute("SELECT COUNT(*) n FROM orders WHERE status='Pending'").fetchone()["n"],
      "bookings":c.execute("SELECT COUNT(*) n FROM bookings").fetchone()["n"],
    }
    c.close()
    parsed=[]
    for o in orders:
        d=dict(o); d["items"]=json.loads(o["items"]); parsed.append(d)
    return render_template("admin_dashboard.html",food_items=items,orders=parsed,bookings=bookings,offers=offers,stats=stats)

@app.route("/admin/food/add",methods=["POST"])
@admin_required
def add_food():
    f=request.files.get("image"); image=None
    if valid_file(f):
        image="uploads/"+secure_filename(f.filename)
        f.save(os.path.join(BASE_DIR,"static",image))
    try: price=float(request.form.get("price","0")); admin_rating=max(0,min(5,float(request.form.get("admin_rating","0"))))
    except: flash("Invalid price or rating.","error"); return redirect(url_for("admin_dashboard"))
    name=request.form.get("name","").strip(); cat=request.form.get("category","Main Course"); desc=request.form.get("description","").strip()
    if not name or price<=0: flash("Name and valid price are required.","error"); return redirect(url_for("admin_dashboard"))
    c=db(); c.execute("""INSERT INTO food_items(name,category,price,description,image,admin_rating,admin_rating_count,rating,rating_count,created_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?)""",(name,cat,price,desc,image,admin_rating,1 if admin_rating else 0,admin_rating,1 if admin_rating else 0,datetime.now().isoformat()))
    c.commit(); c.close(); flash("Food item added.","success"); return redirect(url_for("admin_dashboard"))

@app.route("/admin/food/delete/<int:item_id>",methods=["POST"])
@admin_required
def del_food(item_id):
    c=db(); x=c.execute("SELECT image FROM food_items WHERE id=?",(item_id,)).fetchone(); c.execute("DELETE FROM food_items WHERE id=?",(item_id,)); c.commit(); c.close()
    if x and x["image"]:
        p=os.path.join(BASE_DIR,"static",x["image"])
        if os.path.exists(p): os.remove(p)
    flash("Food item deleted.","success"); return redirect(url_for("admin_dashboard"))

@app.route("/admin/food/toggle/<int:item_id>",methods=["POST"])
@admin_required
def toggle_food(item_id):
    c=db(); c.execute("UPDATE food_items SET available=CASE available WHEN 1 THEN 0 ELSE 1 END WHERE id=?",(item_id,)); c.commit(); c.close(); return redirect(url_for("admin_dashboard"))

@app.route("/admin/order/status/<int:order_id>",methods=["POST"])
@admin_required
def order_status(order_id):
    c=db(); c.execute("UPDATE orders SET status=? WHERE id=?",(request.form.get("status","Pending"),order_id)); c.commit(); c.close(); return redirect(url_for("admin_dashboard"))

@app.route("/admin/booking/status/<int:booking_id>",methods=["POST"])
@admin_required
def booking_status(booking_id):
    c=db(); c.execute("UPDATE bookings SET status=? WHERE id=?",(request.form.get("status","Pending"),booking_id)); c.commit(); c.close(); return redirect(url_for("admin_dashboard"))

@app.route("/admin/offers/add",methods=["POST"])
@admin_required
def add_offer():
    f=request.files.get("poster")
    if not valid_file(f): flash("Please upload a PNG, JPG, WEBP or GIF poster.","error"); return redirect(url_for("admin_dashboard"))
    filename="offer_"+datetime.now().strftime("%Y%m%d%H%M%S")+"_"+secure_filename(f.filename)
    rel="uploads/"+filename; f.save(os.path.join(BASE_DIR,"static",rel))
    c=db(); c.execute("INSERT INTO offers(title,description,poster,active,created_at) VALUES(?,?,?,?,?)",(request.form.get("title","55 Bistro Offer"),request.form.get("description",""),rel,1,datetime.now().isoformat())); c.commit(); c.close()
    flash("Offer poster published.","success"); return redirect(url_for("admin_dashboard"))

@app.route("/admin/offers/toggle/<int:offer_id>",methods=["POST"])
@admin_required
def toggle_offer(offer_id):
    c=db(); c.execute("UPDATE offers SET active=CASE active WHEN 1 THEN 0 ELSE 1 END WHERE id=?",(offer_id,)); c.commit(); c.close(); return redirect(url_for("admin_dashboard"))

@app.route("/admin/offers/delete/<int:offer_id>",methods=["POST"])
@admin_required
def del_offer(offer_id):
    c=db(); x=c.execute("SELECT poster FROM offers WHERE id=?",(offer_id,)).fetchone(); c.execute("DELETE FROM offers WHERE id=?",(offer_id,)); c.commit(); c.close()
    if x:
        p=os.path.join(BASE_DIR,"static",x["poster"])
        if os.path.exists(p): os.remove(p)
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/change-password",methods=["GET","POST"])
@admin_required
def change_password():
    if request.method=="POST":
        old=request.form.get("old_password",""); new=request.form.get("new_password",""); conf=request.form.get("confirm_password","")
        c=db(); a=c.execute("SELECT * FROM admin WHERE username=?",(session["admin_username"],)).fetchone()
        if not a or a["password"]!=old: flash("Old password is incorrect.","error")
        elif new!=conf: flash("New passwords do not match.","error")
        elif len(new)<4: flash("New password must contain at least 4 characters.","error")
        else: c.execute("UPDATE admin SET password=? WHERE username=?",(new,session["admin_username"])); c.commit(); flash("Password updated.","success")
        c.close()
    return render_template("change_password.html")

init_db()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=True)
