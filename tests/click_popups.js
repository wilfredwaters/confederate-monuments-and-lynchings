// Browser test: clicking a mark on the map opens its popup, for victims
// and for monuments. Run by tests/run.html.
window.__tests.push({name:'click popups', run:async function(){
  var wait = function(ms){ return new Promise(function(r){ setTimeout(r, ms); }); };
  var s = document.getElementById('slider'); s.value = 1912; s.oninput(); await wait(100);
  var fails = [];

  // Screen point of a layer, in client coordinates.
  function at(l){
    var p = l._map.latLngToContainerPoint(l.getLatLng());
    var r = l._map.getContainer().getBoundingClientRect();
    var x = r.left + p.x, y = r.top + p.y;
    var inView = p.x > 20 && p.y > 20 && p.x < r.width - 20 && p.y < r.height - 20;

    // Only open map counts: not under the title, warning or other panels.
    var top = inView ? document.elementFromPoint(x, y) : null;
    return {x: x, y: y, inView: !!top && top.tagName === 'CANVAS'};
  }

  // A mark in view and at least `gap` px from every mark in `others`,
  // so the click can only hit it.
  function isolated(group, others, gap){
    var o = [];
    others.eachLayer(function(l){ o.push(at(l)); });
    var found = null;
    group.eachLayer(function(l){
      if(found){ return; }
      var a = at(l);
      if(!a.inView){ return; }
      if(o.every(function(b){ return Math.hypot(a.x - b.x, a.y - b.y) > gap; })){ found = l; }
    });
    return found;
  }

  // Click as a user would: on whatever element is on top at that point.
  async function clickOn(l){
    var a = at(l);
    var el = document.elementFromPoint(a.x, a.y);
    ['mousedown', 'mouseup', 'click'].forEach(function(type){
      el.dispatchEvent(new MouseEvent(type, {clientX:a.x, clientY:a.y, bubbles:true, cancelable:true, view:window}));
    });
    await wait(100);
    var p = document.querySelector('.leaflet-popup-content');
    var text = p ? p.textContent : '';
    l._map.closePopup();
    return text;
  }

  var ml = window.__ml;
  var victim = isolated(ml.lynGroup, ml.monGroup, 20);
  if(!victim){ fails.push('no isolated victim in view'); }
  else if((await clickOn(victim)).indexOf('Killed by a mob') < 0){ fails.push('click on a victim opened no victim popup'); }

  var monument = isolated(ml.monGroup, ml.lynGroup, 10);
  if(!monument){ fails.push('no isolated monument in view'); }
  else if((await clickOn(monument)).indexOf('Whose Heritage') < 0){ fails.push('click on a monument opened no monument popup'); }

  return fails;
}});
