// Browser test for the legend switches, loaded by tests/run.html.
// Writes PASS or the failures into #result.
// Each switch must work on its own, whatever the others are set to.
(async function(){
  var wait = function(ms){ return new Promise(function(r){ setTimeout(r, ms); }); };
  var btn = function(k){ return document.querySelector('#title .k [data-k="'+k+'"]'); };
  var on = function(k){ return btn(k).getAttribute('aria-pressed') === 'true'; };
  var set = async function(k, v){ if(on(k) !== v){ btn(k).click(); await wait(50); } };

  // Removed monuments are drawn with a blue outline (COL.gone).
  var goneShown = function(){
    var n = 0;
    window.__ml.monGroup.eachLayer(function(l){ if(l.options.color === '#1f6fd1'){ n++; } });
    return n;
  };
  var standingShown = function(){
    var n = 0;
    window.__ml.monGroup.eachLayer(function(l){ if(l.options.color !== '#1f6fd1'){ n++; } });
    return n;
  };

  var s = document.getElementById('slider'); s.value = 2024; s.oninput(); await wait(50);
  var fails = [];

  await set('lyn', false); await set('mon', false); await set('gone', true);
  if(goneShown() === 0){ fails.push('removed hidden while Removed is on and Monuments off'); }
  if(standingShown() !== 0){ fails.push('standing shown while Monuments off'); }

  await set('gone', false);
  if(goneShown() !== 0){ fails.push('removed shown while Removed is off'); }

  await set('mon', true);
  if(standingShown() === 0){ fails.push('standing hidden while Monuments on'); }
  if(goneShown() !== 0){ fails.push('removed shown with Monuments on, Removed off'); }

  await set('gone', true); await set('lyn', true);
  var out = fails.length ? 'FAIL\n' + fails.join('\n') : 'PASS';
  document.getElementById('result').textContent = out;
  return out;
})();
